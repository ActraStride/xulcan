"""Base adapter for Vault Store (Secrets Management) providers.

Implements the Template Method pattern for secret retrieval.
Ensures that cross-cutting concerns like logging NEVER leak actual
secret values to the console or telemetry systems.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

logger = logging.getLogger("xulcan.security.vault")

# ── 1. THE CONTRACT (Protocol) ──
@runtime_checkable
class VaultStore(Protocol):
    """Contract for secure secret retrieval (API Keys, DB Passwords)."""
    
    @abstractmethod
    async def get_secret(self, key: str) -> str | None:
        """Retrieves a secret by its key."""
        ...
        
    @abstractmethod
    async def set_secret(self, key: str, value: str) -> None:
        """Stores a secret securely."""
        ...


# ── 2. THE BASE CLASS (Template Method) ──
class BaseVaultStore(VaultStore, ABC):
    """Abstract base class for all Vault providers.
    
    Guarantees that subclasses implement raw retrieval while this class
    handles safe, redacted logging and cache checking.
    """

    async def get_secret(self, key: str) -> str | None:
        """Template method for secure retrieval."""
        logger.debug(f"🔐 VaultStore: Requesting secret '{key}'...")
        
        value = await self._get_secret_impl(key)
        
        if value:
            # Never log the actual secret value, only that it was found and its length.
            logger.debug(f"🔓 VaultStore: Secret '{key}' successfully retrieved (Length: {len(value)}).")
        else:
            logger.warning(f"⚠️ VaultStore: Secret '{key}' not found!")
            
        return value

    async def set_secret(self, key: str, value: str) -> None:
        """Template method for secure storage."""
        logger.debug(f"🔐 VaultStore: Storing secret '{key}' [REDACTED]")
        await self._set_secret_impl(key, value)

    # ── ABSTRACT METHODS FOR SUBCLASSES ──
    @abstractmethod
    async def _get_secret_impl(self, key: str) -> str | None:
        ...

    @abstractmethod
    async def _set_secret_impl(self, key: str, value: str) -> None:
        ...