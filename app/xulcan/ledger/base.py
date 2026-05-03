"""Base adapter for Ledger storage providers.

Implements the Template Method pattern for Event Sourcing repositories.
Provides standardized logging, telemetry interception, and a default 
implementation for computing the RunSummary (The 'Fold'), so concrete 
adapters only need to implement raw I/O operations.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from xulcan.core import MachineID
from xulcan.history.events import RunEvent, RunSummary
from xulcan.kernel.interfaces import EventBus
from xulcan.history.events import RunEvent, RunSummary, RunStatus, EventType

logger = logging.getLogger("xulcan.ledger")


class BaseLedgerAdapter(ABC): # Recuerda: Duck Typing, no hereda de LedgerRepository
    """Abstract base class for all Ledger storage providers."""

    # 1. ⚡ NUEVO: El constructor base acepta el bus opcionalmente
    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus

    # ════════════════════════════════════════════════════════════════════════
    # TEMPLATE METHODS (Cross-Cutting Concerns)
    # ════════════════════════════════════════════════════════════════════════

    async def append(self, event: RunEvent) -> None:
        """Template method that intercepts writes for logging and telemetry."""
        logger.debug(
            f"💾 Appending event {event.type.value} "
            f"[Seq: {event.sequence_number}] for Run {event.run_id}"
        )
        
        # 1. Guardar la verdad inmutable en la BD (Implementado por el hijo)
        await self._append_impl(event)
        
        # 2. ⚡ LA MAGIA: Si hay un Bus conectado, disparamos el Firehose
        if self.event_bus:
            try:
                channel = f"xulcan:firehose:{event.run_id}"
                payload = event.model_dump_json()
                await self.event_bus.publish(channel, payload)
            except Exception as e:
                logger.error(
                    f"🔥 Firehose Error: Failed to broadcast event {event.type.value}. "
                    f"Agent continues. Error: {e}"
                )

    async def get_events(self, run_id: MachineID, from_index: int = 0) -> list[RunEvent]:
        """Template method for reading events."""
        return await self._get_events_impl(run_id, from_index)

    async def tag_run(self, run_id: MachineID, session_key: str) -> None:
        """Template method: tags a run with a human-readable session key."""
        logger.debug(f"🏷️  Session '{session_key}' → Run {run_id}")
        await self._tag_run_impl(run_id, session_key)

    async def get_last_run_id(self, session_key: str) -> MachineID | None:
        """Template method: returns the latest run_id for a given session key."""
        return await self._get_last_run_id_impl(session_key)


    # ════════════════════════════════════════════════════════════════════════
    # ABSTRACT METHODS (To be implemented by Subclasses)
    # ════════════════════════════════════════════════════════════════════════

    @abstractmethod
    async def _append_impl(self, event: RunEvent) -> None:
        """Actual storage logic (SQL INSERT, Redis push, Dict append, etc)."""
        pass

    @abstractmethod
    async def _get_events_impl(self, run_id: MachineID, from_index: int) -> list[RunEvent]:
        """Actual retrieval logic (SQL SELECT, Dict slice, etc)."""
        pass

    @abstractmethod
    async def _tag_run_impl(self, run_id: MachineID, session_key: str) -> None:
        """Persists the session_key → run_id mapping."""
        pass

    @abstractmethod
    async def _get_last_run_id_impl(self, session_key: str) -> MachineID | None:
        """Retrieves the latest run_id associated with a session_key."""
        pass


    # ════════════════════════════════════════════════════════════════════════
    # DEFAULT IMPLEMENTATION (The Fold)
    # ════════════════════════════════════════════════════════════════════════

    async def get_summary(self, run_id: MachineID) -> RunSummary:
        """Default Event Sourcing projection.
        
        Pulls events and computes the state in Python. Subclasses CAN override 
        this if their underlying database can do it faster (e.g., via a SQL View
        or an optimized Postgres query).
        
        Raises:
            KeyError: If the run_id does not exist in the ledger.
        """
        events = await self.get_events(run_id)
        if not events:
            raise KeyError(f"Run {run_id} not found in the Ledger.")
        
        first_event = events[0]
        last_event = events[-1]

        # --- THE FOLD LOGIC ---
        status = RunStatus.RUNNING
        
        if last_event.type == EventType.RUN_CREATED:
            status = RunStatus.CREATED
        elif last_event.type == EventType.RUN_COMPLETED:
            status = RunStatus.COMPLETED
        elif last_event.type == EventType.RUN_FAILED:
            status = RunStatus.FAILED
        elif last_event.type == EventType.HUMAN_INTERVENTION_REQUIRED:
            status = RunStatus.PAUSED

        return RunSummary(
            run_id=run_id,
            status=status,
            step_count=len(events),
            created_at=first_event.timestamp,
            updated_at=last_event.timestamp,
            last_event=last_event
        )