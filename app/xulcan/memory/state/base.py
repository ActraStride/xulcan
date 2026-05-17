"""Base adapter for State Store (Blackboard) providers.

Implements the Template Method pattern for volatile working memory.
Provides standardized logging and lifecycle hooks so that concrete 
adapters (e.g., MemoryStateStore, RedisStateStore) only need to 
implement raw I/O operations.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from xulcan.kernel.interfaces import StateStore
from xulcan.core import MachineID

logger = logging.getLogger("xulcan.memory.base")


class BaseStateStore(StateStore, ABC):
    """Abstract base class for State Store (Blackboard) providers.
    
    Handles cross-cutting concerns like logging and telemetry while
    delegating the actual storage mechanisms to subclasses.
    """
    
    def __init__(self, **kwargs: Any) -> None:
        self.config: dict[str, Any] = kwargs

    # ════════════════════════════════════════════════════════════════════════
    # TEMPLATE METHODS (Cross-Cutting Concerns)
    # ════════════════════════════════════════════════════════════════════════

    async def set(self, run_id: MachineID, key: str, value: Any) -> None:
        """Template method for storing a value."""
        logger.debug(f"📝 StateStore[{run_id}]: Setting key '{key}'")
        await self._set_impl(run_id, key, value)

    async def get(self, run_id: MachineID, key: str) -> Any:
        """Template method for retrieving a value."""
        return await self._get_impl(run_id, key)

    async def exists(self, run_id: MachineID, key: str) -> bool:
        """Template method for checking if a key exists."""
        return await self._exists_impl(run_id, key)

    async def keys(self, run_id: MachineID) -> list[str]:
        """Template method for listing all available keys in a run."""
        return await self._keys_impl(run_id)

    async def delete(self, run_id: MachineID, key: str) -> None:
        """Template method for deleting a specific key."""
        logger.debug(f"🗑️ StateStore[{run_id}]: Deleting key '{key}'")
        await self._delete_impl(run_id, key)

    async def clear(self, run_id: MachineID) -> None:
        """Template method for clearing the entire run's memory."""
        # Logged at DEBUG level because the Kernel already logs GC at INFO level.
        logger.debug(f"🧹 StateStore[{run_id}]: Clearing all memory (Garbage Collection)")
        await self._clear_impl(run_id)

    # ════════════════════════════════════════════════════════════════════════
    # ABSTRACT METHODS (To be implemented by Subclasses)
    # ════════════════════════════════════════════════════════════════════════

    @abstractmethod
    async def _set_impl(self, run_id: MachineID, key: str, value: Any) -> None:
        """Actual storage logic (RAM dict, Redis SET, etc.)."""
        pass

    @abstractmethod
    async def _get_impl(self, run_id: MachineID, key: str) -> Any:
        """Actual retrieval logic. Must return None if key is not found."""
        pass

    @abstractmethod
    async def _exists_impl(self, run_id: MachineID, key: str) -> bool:
        """Actual existence check logic."""
        pass

    @abstractmethod
    async def _keys_impl(self, run_id: MachineID) -> list[str]:
        """Actual key enumeration logic."""
        pass

    @abstractmethod
    async def _delete_impl(self, run_id: MachineID, key: str) -> None:
        """Actual deletion logic. Should fail silently if key doesn't exist."""
        pass

    @abstractmethod
    async def _clear_impl(self, run_id: MachineID) -> None:
        """Actual garbage collection logic for the entire run."""
        pass