"""Local Environment Vault Store implementation.

Fetches secrets from an in-memory dictionary or the OS environment variables.
"""

from __future__ import annotations

import os

from xulcan.memory.vault.base import BaseVaultStore


class MemoryVaultStore(BaseVaultStore):
    """Local implementation of the Vault Store.
    
    Priority:
        1. In-memory secrets passed during initialization.
        2. OS Environment variables.
    
    Future implementations could include HashiCorpVaultStore or AwsSecretsStore,
    which would make network calls in these async methods.
    """
    
    def __init__(self, initial_secrets: dict[str, str] | None = None) -> None:
        self._secrets: dict[str, str] = initial_secrets or {}

    async def _get_secret_impl(self, key: str) -> str | None:
        # Priority 1: Check memory (initialized variables)
        if key in self._secrets:
            return self._secrets[key]
            
        # Priority 2: Fallback to OS environment
        # Convert to standard env var format (e.g., 'gemini_api_key' -> 'GEMINI_API_KEY')
        env_key = key.upper()
        return os.getenv(env_key)

    async def _set_secret_impl(self, key: str, value: str) -> None:
        self._secrets[key] = value