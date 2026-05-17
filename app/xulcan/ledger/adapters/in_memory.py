"""In-Memory Ledger Adapter for local development and testing.

Provides an ephemeral implementation of the LedgerRepository using Python
dictionaries. Data is lost when the process terminates.
"""

from __future__ import annotations

# Importamos el contrato del Bus
from xulcan.kernel.interfaces import EventBus
from xulcan.core import MachineID
from xulcan.history.events import RunEvent, EventType
from xulcan.ledger.base import BaseLedgerAdapter

class InMemoryLedger(BaseLedgerAdapter):
    """Reference implementation using ephemeral RAM storage."""

    # 1. ⚡ Modificamos el constructor para aceptar el bus
    def __init__(self, event_bus: EventBus | None = None) -> None:
        # 2. ⚡ Llamamos al padre para que se guarde el bus y active el Firehose
        super().__init__(event_bus=event_bus)
        
        self._store: dict[MachineID, list[RunEvent]] = {}
        self._sessions: dict[str, MachineID] = {}


    async def _append_impl(self, event: RunEvent) -> None:
        """Writes the event to the in-memory list.
        
        Enforces that the very first event of any run is RUN_CREATED to prevent
        orphan events or corrupted state histories.
        
        Raises:
            ValueError: If attempting to append to a new run with a non-creation event.
        """
        run_id = event.run_id
        
        if run_id not in self._store:
            if event.type != EventType.RUN_CREATED:
                raise ValueError(
                    f"First event for run '{run_id}' must be RUN_CREATED, "
                    f"but got '{event.type.value}'"
                )
            self._store[run_id] = []
            
        self._store[run_id].append(event)

    async def _get_events_impl(self, run_id: MachineID, from_index: int = 0) -> list[RunEvent]:
        """Returns a slice of the events list for a given run."""
        if run_id not in self._store:
            return[]
            
        return self._store[run_id][from_index:]

    async def _tag_run_impl(self, run_id: MachineID, session_key: str) -> None:
        """Associates the session_key with the most recent run_id."""
        self._sessions[session_key] = run_id

    async def _get_last_run_id_impl(self, session_key: str) -> MachineID | None:
        """Returns the latest run_id for the session, or None if it is new."""
        return self._sessions.get(session_key)