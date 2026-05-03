"""In-Memory State Store (Blackboard) implementation.

Provides an ephemeral, ultra-fast implementation of the StateStore using 
Python dictionaries. Data is lost when the process terminates.
"""

from __future__ import annotations

from typing import Any

from xulcan.memory.state.base import BaseStateStore
from xulcan.core import MachineID


class MemoryStateStore(BaseStateStore):
    """In-Memory implementation of the State Store (Blackboard).
    
    Uses Python dictionaries to hold volatile state. Extremely fast, but data
    is lost when the process terminates. Perfect for standalone execution,
    testing, or single-node deployments.
    """
    
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Structure: _storage[run_id][key] = value
        self._storage: dict[MachineID, dict[str, Any]] = {}

    async def _set_impl(self, run_id: MachineID, key: str, value: Any) -> None:
        # Note: Python dictionary assignments are atomic under the GIL.
        # Since there are no 'await' yields during this assignment, 
        # this is 100% asyncio-safe without needing an asyncio.Lock.
        if run_id not in self._storage:
            self._storage[run_id] = {}
        self._storage[run_id][key] = value

    async def _get_impl(self, run_id: MachineID, key: str) -> Any:
        # Use chained gets for safe, non-raising retrieval
        return self._storage.get(run_id, {}).get(key, None)

    async def _exists_impl(self, run_id: MachineID, key: str) -> bool:
        return run_id in self._storage and key in self._storage[run_id]

    async def _keys_impl(self, run_id: MachineID) -> list[str]:
        if run_id not in self._storage:
            return[]
        return list(self._storage[run_id].keys())

    async def _delete_impl(self, run_id: MachineID, key: str) -> None:
        if run_id in self._storage and key in self._storage[run_id]:
            del self._storage[run_id][key]

    async def _clear_impl(self, run_id: MachineID) -> None:
        # Safe pop: Removes the entire run's memory or does nothing if not found.
        self._storage.pop(run_id, None)