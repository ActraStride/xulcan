"""
Wire format for the Xulcan Event Bus.

    signals/types.py    →  BroadcastEvent, IPCMessage  (domain signal atoms)
    signals/envelope.py →  BusEnvelope                 (discriminated union)
                           BusMessage                  (transport envelope)

Why the split within signals/:
    BroadcastEvent and IPCMessage are semantic objects consumed throughout
    kernel/, history/, and mack.py — they carry meaning independent of
    transport. BusMessage is pure infrastructure: it wraps a signal atom
    with the routing metadata the bus needs and owns JSON serialization at
    the wire boundary. Keeping them separate lets consumers import only
    the types they need without pulling in transport concerns.

Publishing::

    signal = BroadcastEvent(run_id=..., event_type=..., data=...)
    msg = BusMessage.from_envelope(signal, channel=f"run:{signal.run_id}")
    await bus.publish(msg.channel, msg.to_wire())

Subscribing::

    async for raw in bus.subscribe(f"run:{run_id}"):
        msg = BusMessage.from_wire(raw)
        match msg.payload:
            case BroadcastEvent(event_type=et):
                handle_broadcast(msg.payload)
            case IPCMessage(channel=ch):
                handle_ipc(msg.payload)

BaseEventBus.publish/subscribe signatures remain (channel: str, message: str)
for backward compatibility. BusMessage owns the typed boundary.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from pydantic import Field, TypeAdapter, field_validator

from xulcan.core.primitives import ImmutableRecord
from .types import BroadcastEvent, IPCMessage


# =============================================================================
# DISCRIMINATED UNION
# =============================================================================

BusEnvelope = Annotated[
    BroadcastEvent | IPCMessage,
    Field(discriminator="type")
]
"""Discriminated union of all signal types that flow through the EventBus.

    "broadcast"  →  BroadcastEvent
    "ipc"        →  IPCMessage

Deserialization::

    from pydantic import TypeAdapter
    from xulcan.signals.envelope import BusEnvelope

    _adapter = TypeAdapter(BusEnvelope)
    envelope = _adapter.validate_python(json.loads(raw_str))

    match envelope:
        case BroadcastEvent(run_id=rid, event_type=et): ...
        case IPCMessage(channel=ch): ...
"""

# Module-level singleton — avoid rebuilding TypeAdapter on every from_wire().
_ENVELOPE_ADAPTER: TypeAdapter[BusEnvelope] = TypeAdapter(BusEnvelope)


# =============================================================================
# TRANSPORT ENVELOPE
# =============================================================================

class BusMessage(ImmutableRecord):
    """Complete typed message that travels over the EventBus wire.

    Wraps a BusEnvelope with the routing metadata required by the bus.

    Attributes:
        channel: EventBus routing key. Convention: "{scope}:{run_id}".
            Stored here so subscribers have routing context after
            deserialization without inspecting envelope internals.
            Not a MachineID — colons are intentional delimiters.
        timestamp: Transport-level timestamp (when message hit the wire).
            Always UTC. Distinct from payload.timestamp (domain
            emission time). Useful for measuring bus latency.
        payload: Typed signal atom:
            "broadcast" → BroadcastEvent
            "ipc"       → IPCMessage

    Example::

        # Publishing
        signal = BroadcastEvent(run_id="abc", event_type="run-created", data={})
        msg = BusMessage.from_envelope(signal, channel="run:abc")
        await bus.publish(msg.channel, msg.to_wire())

        # Subscribing
        async for raw in bus.subscribe("run:abc"):
            msg = BusMessage.from_wire(raw)
            match msg.payload:
                case BroadcastEvent(): ...
                case IPCMessage(): ...
    """

    channel: str = Field(
        min_length=1,
        description=(
            "EventBus routing key. Convention: '{scope}:{run_id}' "
            "(e.g. 'run:abc123', 'ipc:abc123'). "
            "Not validated as MachineID — colons are intentional delimiters."
        )
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description=(
            "Transport-level timestamp (when message hit the bus wire). "
            "Always UTC. Distinct from payload.timestamp (domain emission time)."
        )
    )
    payload: BusEnvelope = Field(
        description=(
            "Typed signal atom discriminated by payload.type: "
            "'broadcast' → BroadcastEvent, 'ipc' → IPCMessage."
        )
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
            raise ValueError("BusMessage.timestamp must be timezone-aware (UTC).")
        return value.astimezone(timezone.utc)

    @classmethod
    def from_envelope(cls, envelope: BusEnvelope, *, channel: str) -> BusMessage:
        """Construct a BusMessage from a typed envelope and a channel name.

        Primary construction path for publishers (Kernel, HumanGate, etc.).

        Args:
            envelope: A BroadcastEvent or IPCMessage to wrap.
            channel: The EventBus channel to publish to.

        Returns:
            A new BusMessage instance wrapping the envelope.
        """
        return cls(channel=channel, payload=envelope)

    @classmethod
    def from_wire(cls, raw: str) -> BusMessage:
        """Deserialize a BusMessage from the raw JSON string off the wire.

        Args:
            raw: JSON string as received from BaseEventBus.subscribe().

        Returns:
            The deserialized BusMessage instance.

        Raises:
            pydantic.ValidationError: If raw is not a valid BusMessage.
            json.JSONDecodeError: If raw is not valid JSON.
        """
        return cls.model_validate(json.loads(raw))

    def to_wire(self) -> str:
        """Serialize to a JSON string for bus.publish().

        Returns:
            JSON string representation of this message.
        """
        return self.model_dump_json()

    @property
    def is_broadcast(self) -> bool:
        """True if the payload is a BroadcastEvent (Kernel domain event).

        Returns:
            True if payload is a BroadcastEvent, False otherwise.
        """
        return isinstance(self.payload, BroadcastEvent)

    @property
    def is_ipc(self) -> bool:
        """True if the payload is an IPCMessage (directed inter-agent message).

        Returns:
            True if payload is an IPCMessage, False otherwise.
        """
        return isinstance(self.payload, IPCMessage)
