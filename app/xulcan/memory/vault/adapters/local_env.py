"""Local OS Environment Vault Store implementation.

Fetches secrets from:
    1. Direct OS Environment variables (e.g. GEMINI_API_KEY).
    2. Docker Secrets / File-based secrets (via the _FILE suffix convention).
"""

from __future__ import annotations

import os
import logging
from pathlib import Path

from xulcan.memory.vault.base import BaseVaultStore

logger = logging.getLogger("xulcan.vault.env")


class LocalEnvVaultStore(BaseVaultStore):
    """Vault Store for real-world local and containerized environments.
    
    This adapter is the standard for production deployments. It follows 
    cloud-native patterns for secret injection.
    
    Resolution Strategy:
        1. Look for environment variable: {KEY.upper()}
        2. If not found, look for: {KEY.upper()}_FILE
        3. If {KEY.upper()}_FILE exists, read the content of the file path it points to.
    """

    def __init__(self, **_kwargs) -> None:
        # No requiere inicialización especial, todo viene del S.O.
        pass

    async def _get_secret_impl(self, key: str) -> str | None:
        """Resolves the secret from the OS or filesystem."""
        env_key = key.upper()
        
        # ── 1. Intento directo (Variable de Entorno) ─────────────────────
        direct_value = os.getenv(env_key)
        if direct_value:
            return direct_value

        # ── 2. Intento vía Docker Secret (Path en _FILE) ─────────────────
        # Ejemplo: si busca GEMINI_API_KEY, mira si existe GEMINI_API_KEY_FILE
        file_path_var = os.getenv(f"{env_key}_FILE")
        
        if file_path_var:
            path = Path(file_path_var)
            if path.exists() and path.is_file():
                try:
                    # Leer archivo, limpiar espacios/saltos de línea
                    content = path.read_text(encoding="utf-8").strip()
                    if content:
                        logger.debug(f"🔐 Secret '{env_key}' loaded from file: {path}")
                        return content
                except Exception as e:
                    logger.error(
                        f"❌ Error reading secret file for '{env_key}' at {path}: {str(e)}"
                    )
        
        return None

    async def _set_secret_impl(self, key: str, value: str) -> None:
        """Sets a secret in the current process environment.
        
        NOTE: This only affects the current running process, not the 
        actual OS/Docker environment persistently.
        """
        os.environ[key.upper()] = value