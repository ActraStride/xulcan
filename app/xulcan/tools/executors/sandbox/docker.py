"""Docker-based Sandbox Isolation Provider.

Stateless implementation of the IsolationProvider using the Docker Engine.
It does not maintain in-memory dictionaries; the Docker Daemon itself acts 
as the single source of truth for session state.
"""

from __future__ import annotations

import logging
import asyncio
import base64
import shlex
from typing import Any

import docker
from docker.errors import DockerException, NotFound, APIError

from xulcan.tools.executors.sandbox.provider import IsolationProvider

logger = logging.getLogger("xulcan.tools.sandbox.docker")


class DockerProvider(IsolationProvider):
    """Stateless Docker sandbox engine.
    
    Provides ephemeral, secure execution environments for LLM tool calls.
    Enforces resource limits and execution timeouts to prevent DoS attacks.
    """

    client: docker.DockerClient
    image: str
    prefix: str

    def __init__(self, image: str = "python:3.11-slim") -> None:
        try:
            self.client = docker.from_env()
            self.image = image
            self.prefix = "xulcan_sandbox_"
            logger.debug(f"🐳 DockerProvider (Stateless) initialized. Image: '{self.image}'")
        except DockerException as e:
            logger.critical(f"❌ Failed to connect to the Docker daemon: {e}")
            raise

    def _get_container_name(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    async def is_active(self, session_id: str) -> bool:
        """Queries the Docker daemon to check if the session container is running."""
        name = self._get_container_name(session_id)
        
        def _check() -> bool:
            try:
                container = self.client.containers.get(name)
                return container.status == "running"
            except NotFound:
                return False
                
        return await asyncio.to_thread(_check)

    async def start_session(
        self, 
        session_id: str, 
        workspace_path: str | None = None
    ) -> None:
        """Initializes or wakes up a secure container for the session."""
        if await self.is_active(session_id):
            return

        name = self._get_container_name(session_id)
        
        def _start() -> None:
            volumes = {}
            if workspace_path:
                volumes[workspace_path] = {'bind': '/workspace', 'mode': 'rw'}
            
            # The Master Trick: 'tail -f /dev/null' consumes 0% CPU but keeps the container alive.
            # Security: mem_limit and nano_cpus prevent malicious LLM code from crashing the host.
            self.client.containers.run(
                self.image,
                command="tail -f /dev/null",
                detach=True,
                working_dir="/workspace",
                volumes=volumes,
                name=name,
                auto_remove=True,
                network_mode="bridge",
                mem_limit="512m",           # Prevent RAM exhaustion
                nano_cpus=1000000000        # Limit to 1 CPU core (1 billion nano-CPUs)
            )

        try:
            await asyncio.to_thread(_start)
            logger.debug(f"🟢 Container '{name}' started.")
        except APIError as e:
            # HTTP 409 Conflict: Another concurrent thread/process just started it.
            if e.response is not None and e.response.status_code == 409:
                logger.debug(f"⚡ Container '{name}' was already started by a parallel process.")
            else:
                logger.error(f"❌ Error starting session {session_id}: {e}")
                raise
        except Exception as e:
            logger.error(f"❌ Error starting session {session_id}: {e}")
            raise

    async def execute_command(
        self, 
        session_id: str, 
        command: str, 
        timeout: int = 30
    ) -> dict[str, Any]:
        """Executes a command inside the container with strict timeouts."""
        name = self._get_container_name(session_id)

        def _exec() -> dict[str, Any]:
            try:
                container = self.client.containers.get(name)
            except NotFound:
                raise RuntimeError(f"Session '{session_id}' is not active in Docker.")

            # Security: Wrap the entire bash execution in Linux 'timeout'.
            # Prevents pipe bypasses (e.g. 'echo a | sleep 100') from hanging the thread.
            cmd_array =["timeout", str(timeout), "bash", "-c", command]

            # Demux correctly separates stdout from stderr at the binary level
            exit_code, output = container.exec_run(
                cmd=cmd_array,
                demux=True
            )
            
            # Exit code 124 is the standard Linux return code for a timeout
            if exit_code == 124:
                return {
                    "exit_code": 124,
                    "stdout": "",
                    "stderr": f"Execution killed: Exceeded {timeout} seconds timeout limit."
                }
            
            stdout = output[0].decode("utf-8") if output and output[0] else ""
            stderr = output[1].decode("utf-8") if output and output[1] else ""
            
            return {"exit_code": exit_code, "stdout": stdout, "stderr": stderr}

        return await asyncio.to_thread(_exec)

    async def read_file(self, session_id: str, file_path: str) -> str:
        """Reads a file from the container's isolated filesystem."""
        safe_path = shlex.quote(file_path)
        result = await self.execute_command(session_id, f"cat {safe_path}")
        
        if result["exit_code"] != 0:
            raise FileNotFoundError(f"Error reading {file_path}: {result['stderr']}")
        return result["stdout"]

    async def write_file(self, session_id: str, file_path: str, content: str) -> None:
        """Bulletproof file writing using Base64 to bypass bash escaping nightmares."""
        safe_path = shlex.quote(file_path)
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        command = f"echo '{encoded}' | base64 -d > {safe_path}"
        
        result = await self.execute_command(session_id, command)
        if result["exit_code"] != 0:
            raise IOError(f"Error writing to {file_path}: {result['stderr']}")

    async def terminate_session(self, session_id: str) -> None:
        """Stops and destroys the container."""
        name = self._get_container_name(session_id)

        def _stop() -> None:
            try:
                container = self.client.containers.get(name)
                # Stop triggers removal because auto_remove=True was set on run()
                container.stop(timeout=2) 
            except NotFound:
                pass 

        await asyncio.to_thread(_stop)
        logger.info(f"🛑 Session '{session_id}' terminated and destroyed.")