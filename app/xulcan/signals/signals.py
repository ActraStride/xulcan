"""
Signal atoms for the Xulcan Event Bus.

Defines the two fundamental signal kinds that flow through the EventBus:

    BroadcastEvent — 1-to-N. The Kernel announces what just happened.
                     Kernel → World. Past tense. Zero coupling to consumers.

    IPCMessage     — 1-to-1. A named participant sends a directed message
                     to a specific run. World → Kernel, or Agent → Agent.
                     If lost, the target run may stall indefinitely.

Both types depend only on ``core/`` primitives. They are sibling atoms to
the LLM protocol types in ``protocol/`` and the ledger event types in
``history/`` — none of those three layers imports from the others.

Envelope Pattern:
    ``BroadcastEvent.data`` and ``IPCMessage.payload`` are typed as
    ``JsonDict`` rather than concrete domain objects. This keeps
    ``signals/`` decoupled from ``history/`` (no circular imports) and
    makes deserialization opt-in — consumers that only route on
    ``event_type`` or ``channel`` pay no Pydantic validation cost.

    To recover the full typed event from a BroadcastEvent::

        from xulcan.history.events import RunEvent
        event = RunEvent.model_validate(signal.data)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, field_validator

from xulcan.core.primitives import ImmutableRecord, MachineID, JsonDict


# =============================================================================
# BROADCAST EVENT  (1-to-N, Kernel → World)
# =============================================================================

class BroadcastEvent(ImmutableRecord):
    """A 1-to-N signal emitted by the Kernel on every domain action.

    The Kernel emits and forgets — it does not know or care whether zero,
    one, or a thousand consumers are subscribed. Consumers (dashboards,
    audit loggers, Nexus) react asynchronously.

    Contrast with IPCMessage:
        BroadcastEvent  →  1-to-N, "this just happened", Kernel → World.
        IPCMessage      →  1-to-1, "do this / here is your data", directed.

    Attributes:
        type: Discriminator for BusEnvelope (always "broadcast").
        run_id: Run this event belongs to. Primary routing key.
        event_type: Event category (e.g. "run-created", "tool-output").
            Structurally a MachineID; semantically an EventType
            value from ``history/``. Narrow when needed with
            ``EventType(signal.event_type)``.
        data: Serialized RunEvent payload (Envelope Pattern).
            Deserialize with ``RunEvent.model_validate(signal.data)``
            only when the typed event is actually needed.
        timestamp: When this signal was emitted (always UTC).

    Example::

        signal = BroadcastEvent(
            run_id="run-abc123",
            event_type="model-response",
            data=event.model_dump(),
        )
        msg = BusMessage.from_envelope(signal, channel=f"run:{signal.run_id}")
        await bus.publish(msg.channel, msg.to_wire())
    """

    type: Literal["broadcast"] = "broadcast"

    run_id: MachineID = Field(
        description="Run this event belongs to. Primary routing key for consumers."
    )
    event_type: MachineID = Field(
        description=(
            "Event category (e.g. 'run-created', 'tool-output'). "
            "Structurally a MachineID; semantically an EventType enum value. "
            "Callers may narrow with EventType(signal.event_type)."
        )
    )
    data: JsonDict = Field(
        description=(
            "Serialized RunEvent payload (Envelope Pattern). "
            "Full schema lives in history/events.py. "
            "Deserialize with RunEvent.model_validate(signal.data) "
            "only if you need the typed event — this cost is opt-in."
        )
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this signal was emitted (always UTC)."
    )

    @field_validator("timestamp", mode="after")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        """Ensures the timestamp is timezone-aware and normalized to UTC.

        Args:
            value: The datetime value to validate.

        Returns:
            The validated datetime normalized to UTC timezone.

        Raises:
            ValueError: If the timestamp is naive (no timezone info).
        """
        if value.tzinfo is None:
            raise ValueError("BroadcastEvent.timestamp must be timezone-aware (UTC).")
        return value.astimezone(timezone.utc)


# =============================================================================
# IPC MESSAGE  (1-to-1, directed)
# =============================================================================

class IPCMessage(ImmutableRecord):
    """A 1-to-1 directed message addressed to a specific run on a named channel.

    Unlike BroadcastEvent, an IPCMessage has a named destination. If it is
    lost or ignored the target run may stall indefinitely — a Kernel
    suspended at a HumanGate will never resume without the approval
    IPCMessage arriving on its channel.

    Contrast with BroadcastEvent:
        BroadcastEvent  →  1-to-N, "this just happened", Kernel → World.
        IPCMessage      →  1-to-1, "do this / here is your data", directed.

    Channel convention:
        "{scope}:{run_id}"           e.g. "human-gate:abc123"
        "{scope}:{run_id}:{sub_id}"  e.g. "fsm:parent123:child456"
        Colons are intentional delimiters — channel is not a MachineID.

    Current use cases:
        - Human operator injects approval into a suspended run
          (channel: "human-gate:{run_id}")
        - External webhook delivers its result to a waiting run
          (channel: "webhook:{run_id}")

    Planned (v2):
        - Parent agent → child FSM instructions
          (channel: "fsm:{parent_run_id}:{child_run_id}")
        - Child FSM → parent completion report
          (channel: "fsm:{parent_run_id}:result")

    Attributes:
        type: Discriminator for BusEnvelope (always "ipc").
        run_id: Target run this message is addressed to.
        sender: Logical identity of the sender (e.g. "human-operator",
            "webhook-callback", a parent agent's run_id).
        channel: Named logical address. Not a MachineID (colons allowed).
        payload: Message content. Schema is channel-specific.
        timestamp: When this message was sent (always UTC).

    Example::

        msg = IPCMessage(
            run_id="run-abc123",
            sender="human-operator",
            channel="human-gate:run-abc123",
            payload={"decision": "approved", "feedback": "Looks good."},
        )
        envelope = BusMessage.from_envelope(msg, channel=msg.channel)
        await bus.publish(envelope.channel, envelope.to_wire())
    """

    type: Literal["ipc"] = "ipc"

    run_id: MachineID = Field(
        description="Target run this message is addressed to."
    )
    sender: MachineID = Field(
        description=(
            "Logical identity of the sender "
            "(e.g. 'human-operator', 'webhook-callback', parent run_id)."
        )
    )
    channel: str = Field(
        min_length=1,
        description=(
            "Named logical address. Convention: '{scope}:{run_id}' "
            "(e.g. 'human-gate:abc123', 'webhook:abc123', 'fsm:parent:child'). "
            "Not validated as MachineID — colons are intentional delimiters."
        )
    )
    payload: JsonDict = Field(
        description=(
            "Message content. Schema is channel-specific. "
            "HumanGate payloads carry decision + feedback; "
            "webhook payloads carry the raw callback body."
        )
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this message was sent (always UTC)."
    )

    @field_validator("timestamp", mode="after")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        """Ensures the timestamp is timezone-aware and normalized to UTC.

        Args:
            value: The datetime value to validate.

        Returns:
            The validated datetime normalized to UTC timezone.

        Raises:
            ValueError: If the timestamp is naive (no timezone info).
        """
        if value.tzinfo is None:
            raise ValueError("IPCMessage.timestamp must be timezone-aware (UTC).")
        return value.astimezone(timezone.utc)