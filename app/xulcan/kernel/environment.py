"""SystemEnvironment — The execution context and dependency container (DEFINITIVE VERSION).

Manages cross-cutting volatile state, secrets, real-time messaging, and physical
environment configuration. Injected into the Kernel, Router, and Executors — any
component that needs to read/write agent memory, fetch credentials, emit
telemetry, or access workspace configuration.

FIXED ISSUES:
    - Semaphore moved to instance attribute (prevents memory leak)
"""

from __future__ import annotations

import asyncio
from typing import Any

from xulcan.core import MachineID
from xulcan.kernel.interfaces import StateStore, EventBus

# VaultStore might not be in interfaces, handle gracefully
try:
    from xulcan.kernel.interfaces import VaultStore
except ImportError:
    VaultStore = None


class SystemEnvironment:
    """The shared environment context for a Xulcan deployment.

    Analogous to a power strip: provides the same 'outlets' (state_store,
    vault_store, event_bus, workspace_id) to every component that plugs into it.

    Components that receive SystemEnvironment:
        - ProtoKernel: renders system_prompt with memory.
        - ToolRouterExecutor: resolves Jinja2 variables in tool args.
        - LocalPythonExecutor: injects run_id, state_store, and event_bus into tools.
        - SandboxExecutor: determines workspace_id for container sessions.
        - SubAgentExecutor: coordinates memory and IPC signals between parent and child runs.
    """

    # ✅ FIX: Class-level semaphore limit as constant
    _MAX_CONCURRENT_GETS = 50

    def __init__(
        self,
        state_store: StateStore,
        vault_store: Any = None,  # VaultStore | None
        event_bus: Any = None,    # EventBus | None
        workspace_id: str | None = None
    ):
        self.state_store = state_store
        self.vault_store = vault_store
        self.event_bus = event_bus
        self.workspace_id = workspace_id

        # ✅ FIX: Semaphore as instance attribute (not created on each call)
        self._semaphore = asyncio.Semaphore(self._MAX_CONCURRENT_GETS)

    async def resolve_memory(self, run_id: MachineID) -> dict[str, Any]:
        """Loads all current StateStore keys into a dictionary for Jinja2 rendering.

        This is the canonical way to get the full memory context for template
        rendering. Avoids duplicating this pattern across the Kernel and Router.

        Performance Note:
            Uses asyncio.gather for concurrent retrieval of all keys, maximizing
            I/O performance for remote stores (e.g., Redis).

        Args:
            run_id: The current execution run identifier.

        Returns:
            Dictionary mapping key → value for all variables in this run's memory.
        """
        if not self.state_store:
            return {}

        keys = await self.state_store.keys(run_id)
        if not keys:
            return {}

        # ✅ FIX: Use instance semaphore instead of creating new one each call
        async def _safe_get(k: str) -> Any:
            async with self._semaphore:
                return await self.state_store.get(run_id, k)

        values = await asyncio.gather(*(_safe_get(k) for k in keys))

        return dict(zip(keys, values))
