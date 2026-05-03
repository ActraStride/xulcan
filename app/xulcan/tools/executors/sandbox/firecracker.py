import os
import json
import logging
import asyncio
import shutil
import httpx  # Necesario para peticiones HTTP sobre UNIX Sockets
import asyncssh # Necesario para ejecutar comandos dentro de la MicroVM
from typing import Dict, Any, Optional

from xulcan.tools.executors.sandbox.provider import IsolationProvider

logger = logging.getLogger("xulcan.tools.sandbox.firecracker")

class FirecrackerProvider(IsolationProvider):
    """
    Implementación Stateless para Firecracker MicroVMs.
    Provee aislamiento a nivel de hardware (KVM) en milisegundos.
    """

    def __init__(
        self, 
        kernel_path: str = "/opt/firecracker/vmlinux",
        rootfs_base: str = "/opt/firecracker/ubuntu-rootfs.ext4",
        fc_binary: str = "firecracker"
    ):
        self.kernel_path = kernel_path
        self.rootfs_base = rootfs_base
        self.fc_binary = fc_binary
        self.socket_dir = "/tmp/xulcan_fc"
        
        os.makedirs(self.socket_dir, exist_ok=True)
        logger.info("🧨 FirecrackerProvider inicializado. Aislamiento nivel Hardware listo.")

    def _get_socket_path(self, session_id: str) -> str:
        return f"{self.socket_dir}/{session_id}.sock"

    def _get_drive_path(self, session_id: str) -> str:
        # Cada microVM necesita su propia copia física del disco duro (Copy-on-Write)
        return f"{self.socket_dir}/{session_id}_rootfs.ext4"

    # =========================================================================
    # COMUNICACIÓN CON EL API DEL SOCKET DE FIRECRACKER
    # =========================================================================
    async def _api_put(self, socket_path: str, endpoint: str, payload: dict) -> None:
        """Envía comandos de configuración a la MicroVM a través del socket UNIX."""
        transport = httpx.AsyncHTTPTransport(uds=socket_path)
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.put(
                f"http://localhost{endpoint}", 
                json=payload, 
                timeout=5.0
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Firecracker API Error ({endpoint}): {response.text}")

    # =========================================================================
    # IMPLEMENTACIÓN DEL CONTRATO XULCAN
    # =========================================================================
    async def is_active(self, session_id: str) -> bool:
        """Verifica si el socket existe y responde."""
        sock_path = self._get_socket_path(session_id)
        if not os.path.exists(sock_path):
            return False
        try:
            # Si el API de la máquina responde, está viva
            transport = httpx.AsyncHTTPTransport(uds=sock_path)
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.get("http://localhost/machine-config", timeout=1.0)
                return resp.status_code == 200
        except Exception:
            return False

    async def start_session(self, session_id: str, workspace_path: Optional[str] = None) -> None:
        if await self.is_active(session_id):
            return

        sock_path = self._get_socket_path(session_id)
        drive_path = self._get_drive_path(session_id)

        # 1. Clonar el disco base para esta sesión específica
        await asyncio.to_thread(shutil.copy2, self.rootfs_base, drive_path)

        # 2. Levantar el proceso Firecracker en segundo plano apuntando al socket
        # (El proceso nace pausado esperando configuración)
        cmd = f"{self.fc_binary} --api-sock {sock_path}"
        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        
        # Darle 100ms a Firecracker para crear el socket físico
        await asyncio.sleep(0.1) 

        try:
            # 3. Configurar Hardware Virtual (1 vCPU, 256MB RAM)
            await self._api_put(sock_path, "/machine-config", {
                "vcpu_count": 1,
                "mem_size_mib": 256,
                "ht_enabled": False
            })

            # 4. Inyectar el Kernel de Linux
            await self._api_put(sock_path, "/boot-source", {
                "kernel_image_path": self.kernel_path,
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off"
            })

            # 5. Montar el Disco Duro (Rootfs)
            await self._api_put(sock_path, "/drives/rootfs", {
                "drive_id": "rootfs",
                "path_on_host": drive_path,
                "is_root_device": True,
                "is_read_only": False
            })

            # TODO: Configurar red (TAP interface) aquí para tener internet
            # await self._api_put(sock_path, "/network-interfaces/eth0", {...})

            # 6. 🚀 ARRANCAR EL MOTOR
            await self._api_put(sock_path, "/actions", {
                "action_type": "InstanceStart"
            })
            
            # Darle 2 segundos a Linux para que termine de bootear dentro de la VM
            await asyncio.sleep(2.0)
            logger.info(f"🟢 MicroVM Firecracker encendida para sesión {session_id}")

        except Exception as e:
            logger.error(f"Fallo al iniciar Firecracker: {e}")
            await self.terminate_session(session_id)
            raise

    async def execute_command(self, session_id: str, command: str, timeout: int = 30) -> Dict[str, Any]:
        if not await self.is_active(session_id):
            raise RuntimeError(f"La sesión {session_id} no está activa.")

        # Como es una VM real, no podemos inyectar comandos desde afuera como en Docker.
        # Tenemos que entrar por SSH a la IP asignada a esta MicroVM.
        # (Asumiendo que configuramos una IP predecible basada en el session_id)
        vm_ip = "192.168.100.2" # Simplificación para el ejercicio
        
        try:
            # Conexión SSH asíncrona (Requiere que el rootfs tenga servidor SSH encendido)
            async with asyncssh.connect(vm_ip, username="root", password="root_password", known_hosts=None) as conn:
                result = await conn.run(command, check=False, timeout=timeout)
                
                return {
                    "exit_code": result.exit_status,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
        except asyncssh.TimeoutError:
            return {"exit_code": 124, "stdout": "", "stderr": "Command timed out"}
        except Exception as e:
            raise RuntimeError(f"Error SSH en la VM: {str(e)}")

    async def read_file(self, session_id: str, file_path: str) -> str:
        result = await self.execute_command(session_id, f"cat {file_path}")
        if result["exit_code"] != 0:
            raise FileNotFoundError(result["stderr"])
        return result["stdout"]

    async def write_file(self, session_id: str, file_path: str, content: str) -> None:
        import base64
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        command = f"echo '{encoded}' | base64 -d > {file_path}"
        result = await self.execute_command(session_id, command)
        if result["exit_code"] != 0:
            raise IOError(result["stderr"])

    async def terminate_session(self, session_id: str) -> None:
        sock_path = self._get_socket_path(session_id)
        drive_path = self._get_drive_path(session_id)

        # Matar la máquina usando el API
        if os.path.exists(sock_path):
            try:
                await self._api_put(sock_path, "/actions", {"action_type": "SendCtrlAltDel"})
                await asyncio.sleep(0.5)
            except Exception:
                pass
            finally:
                # Limpiar socket
                try: os.remove(sock_path)
                except OSError: pass

        # Borrar el disco duro clonado
        if os.path.exists(drive_path):
            try: os.remove(drive_path)
            except OSError: pass
            
        logger.info(f"🛑 MicroVM Firecracker {session_id} destruida.")