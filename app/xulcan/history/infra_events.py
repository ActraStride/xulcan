"""
Infrastructure-layer events for Xulcan.

This module defines typed, immutable events that capture cross-cutting
infrastructure concerns: state persistence, secret access, provider fallbacks,
budget notifications, and governance audit trails.

Design decision — separate from history/events.py:
    RunEvents (in history/events.py) are positioned within the agent's
    execution loop — each carries a `step_index` that places it in the
    cognitive timeline of a run.

    InfraEvents are orthogonal to that timeline. A FallbackFired event
    doesn't belong to step N — it describes what the transport layer did
    before step N could even start. Mixing them would force artificial
    step_index values (0? -1?) onto events that have no logical position
    in the agent loop.

    BaseInfraEvent mirrors the structure of BaseRunEvent (ImmutableRecord,
    run_id, UTC timestamp) but intentionally omits step_index.

Layer contract:
    history/infra_events.py imports from:
        core/primitives.py  — ImmutableRecord, MachineID, ContextKey, SemanticText
        core/signals.py     — FirehosePayload (for envelope construction at bus boundary)

    history/infra_events.py does NOT import from:
        history/events.py   — avoids circular imports; infra events are structurally
                              independent of run events.
        kernel/             — infra events are emitted BY kernel components but
                              defined independently of them.

Emitters by event type:
    StateWritten          — StateManager / context hooks (write path)
    VaultAccessed         — CredentialProxy / VaultProvider
    FallbackFired         — LLM provider layer (UnifiedResponse fallback path)
    BudgetNotified        — BursarStrategy (SOFT_NOTIFY verdict path)
    ToolGovernanceApplied — Kernel (CHECKING_POLICY state, per tool call)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from enum import Enum

from pydantic import Field, field_validator

from xulcan.core.primitives import (
    ImmutableRecord,
    MachineID,
    ContextKey,
    SemanticText,
)


class InfraEventType(str, Enum):
    """Enumeración de tipos de eventos de infraestructura."""
    STATE_WRITTEN = "state_written"
    VAULT_ACCESSED = "vault_accessed"
    FALLBACK_FIRED = "fallback_fired"
    BUDGET_NOTIFIED = "budget_notified"
    TOOL_GOVERNANCE_APPLIED = "tool_governance_applied"


# ═══════════════════════════════════════════════════════════════════════════
# BASE INFRASTRUCTURE EVENT
# ═══════════════════════════════════════════════════════════════════════════

class BaseInfraEvent(ImmutableRecord):
    """Immutable base for all infrastructure-layer events.

    Mirrors BaseRunEvent's structure (ImmutableRecord + run_id + UTC timestamp)
    but deliberately omits `step_index`.

    Rationale for omitting step_index:
        InfraEvents describe what infrastructure components did in service of
        a run — they are not positioned within the agent's cognitive loop.
        A FallbackFired event has no meaningful step_index because it occurs
        at the transport layer, before the Kernel's loop iteration completes.
        Forcing a step_index would either be wrong (0? -1?) or misleading.

    All subclasses must define a `type` field with a unique Literal value —
    this is the discriminator for the InfraEvent union below.
    """
    run_id: MachineID = Field(
        description="Run this event belongs to. Primary routing and storage key."
    )
    # ✅ AÑADIR ESTE CAMPO:
    sequence_number: int = Field(
        ge=1,
        description="Monotonic counter for global ordering in the Ledger."
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this event was emitted (always UTC)."
    )

    @field_validator("timestamp", mode="after")
    @classmethod
    def validate_timestamp_is_utc(cls, value: datetime) -> datetime:
        """Reject naive datetimes. Mirrors BaseRunEvent.validate_timestamp_is_utc."""
        if value.tzinfo is None:
            raise ValueError(
                "InfraEvent.timestamp must be timezone-aware (UTC). "
                "Use datetime.now(timezone.utc) or attach tzinfo explicitly."
            )
        return value.astimezone(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# CONCRETE INFRA EVENTS
# ═══════════════════════════════════════════════════════════════════════════

class StateWritten(BaseInfraEvent):
    """Emitted when a context value is written to persistent state.

    Enables audit trails for stateful agents: which hook wrote what key,
    and when. Intentionally does NOT capture the written value — values may
    be arbitrarily large or sensitive.

    Emitter: StateManager (or equivalent write path in context hooks).

    Example:
        StateWritten(
            run_id="run-abc123",
            key="conversation_summary",
            source_hook="summarize-after-step"
        )
    """
    type: Literal[InfraEventType.STATE_WRITTEN] = InfraEventType.STATE_WRITTEN

    key: ContextKey = Field(
        description=(
            "Context key that was written. "
            "Validated as ContextKey — must be a valid programmatic identifier."
        )
    )
    source_hook: MachineID = Field(
        description=(
            "Lifecycle hook that triggered this write "
            "(e.g. 'summarize-after-step', 'persist-tool-output'). "
            "Identifies the write origin for debugging and audit."
        )
    )


class VaultAccessed(BaseInfraEvent):
    """Emitted when a secret is retrieved from the credential vault.

    Provides a tamper-evident audit trail for credential access without
    ever recording the secret value itself. The secret_key field identifies
    WHAT was accessed; the value is never present in any event payload.

    Emitter: CredentialProxy / VaultProvider (read path).

    Security note:
        This event intentionally omits the secret value, expiry, rotation
        status, and all other credential metadata. The audit trail records
        access patterns only — not credential contents.

    Example:
        VaultAccessed(
            run_id="run-abc123",
            secret_key="openai-api-key",
            accessor="openai-adapter"
        )
    """
    type: Literal[InfraEventType.VAULT_ACCESSED] = InfraEventType.VAULT_ACCESSED

    secret_key: MachineID = Field(
        description=(
            "Logical key identifying which secret was accessed "
            "(e.g. 'openai-api-key', 'slack-webhook-token'). "
            "NEVER the secret value itself."
        )
    )
    accessor: MachineID = Field(
        description=(
            "Component that requested the secret "
            "(e.g. an adapter's MachineID, a tool's MachineID). "
            "Identifies the consumer for access-pattern auditing."
        )
    )


class FallbackFired(BaseInfraEvent):
    """Emitted when the provider layer falls back to an alternate LLM.

    Today, provider fallback information is buried in `provider_metadata`
    inside UnifiedResponse — it is effectively invisible to the event log
    and the Ledger. FallbackFired surfaces this as a first-class infra event
    so operators can observe and alert on degraded provider availability.

    Emitter: LLM provider layer (wherever UnifiedResponse.fallback_used is set).

    Example:
        FallbackFired(
            run_id="run-abc123",
            failed_provider="anthropic",
            next_provider="openai",
            reason="429 rate limit exceeded after 3 retries"
        )
    """
    type: Literal[InfraEventType.FALLBACK_FIRED] = InfraEventType.FALLBACK_FIRED

    failed_provider: MachineID = Field(
        description=(
            "Provider that failed and triggered the fallback "
            "(maps to ProviderRegistry key, same as ModelSpec.provider)."
        )
    )
    next_provider: MachineID = Field(
        description=(
            "Provider selected as the fallback target "
            "(maps to ProviderRegistry key)."
        )
    )
    reason: SemanticText = Field(
        description=(
            "Human-readable explanation of why the fallback fired "
            "(e.g. '429 rate limit exceeded', 'connection timeout after 3 retries'). "
            "Validated as SemanticText — preserves whitespace, no length abuse."
        )
    )


class BudgetNotified(BaseInfraEvent):
    """Emitted when a run's token consumption crosses a SOFT_NOTIFY threshold.

    Today, BudgetStrategy.SOFT_NOTIFY produces a BursarVerdict.WARN that
    silently falls through the kernel without being recorded anywhere. This
    event makes that signal observable: operators can subscribe to
    BudgetNotified events for alerting, dashboards, and cost analytics.

    Emitter: BursarStrategy (the SOFT_NOTIFY / WARN verdict path).

    Note on HARD_CAP:
        Hard cap breaches result in a BudgetExceededError being raised, which
        causes a RunFailed event (a RunEvent, not an InfraEvent). BudgetNotified
        is only for soft notifications — the run continues after this event.

    Example:
        BudgetNotified(
            run_id="run-abc123",
            current_tokens=47_500,
            limit=50_000
        )
    """
    type: Literal[InfraEventType.BUDGET_NOTIFIED] = InfraEventType.BUDGET_NOTIFIED

    current_tokens: int = Field(
        ge=0,
        description="Total tokens consumed by this run at the time of notification."
    )
    limit: int = Field(
        gt=0,
        description=(
            "Token limit that was exceeded (the SOFT_NOTIFY threshold). "
            "current_tokens > limit when this event is emitted."
        )
    )


class ToolGovernanceApplied(BaseInfraEvent):
    """Emitted after governance is evaluated for a tool call.

    Records which governance strategies were active for a specific tool call
    in a specific run. This is the per-tool-call audit trail required for
    enterprise compliance: "prove that tool X was governed by policy Y
    when it executed at time T."

    Emitted regardless of the governance outcome (APPROVED, BLOCKED, ESCALATE)
    — the outcome is captured in the subsequent RunEvent (ToolOutput, or a
    SentinelVerdict in a future event schema extension).

    Emitter: Kernel (CHECKING_POLICY state, immediately after evaluating
    tool_config.governance for the current tool call).

    Example:
        ToolGovernanceApplied(
            run_id="run-abc123",
            tool_name="send-email",
            human_gate_strategy="terminal",
            sentinel_strategy="blocklist"
        )
    """
    type: Literal[InfraEventType.TOOL_GOVERNANCE_APPLIED] = InfraEventType.TOOL_GOVERNANCE_APPLIED

    tool_name: MachineID = Field(
        description=(
            "Tool whose governance was evaluated "
            "(matches AgentToolConfig.name / the @tool decorator name)."
        )
    )
    human_gate_strategy: MachineID = Field(
        description=(
            "HumanGate strategy active for this tool call "
            "(maps to HumanGateRegistry key, e.g. 'auto_approve', 'terminal', 'webhook'). "
            "Sourced from tool_config.governance.human_gate.strategy."
        )
    )
    sentinel_strategy: MachineID = Field(
        description=(
            "Sentinel strategy active for this tool call "
            "(maps to SentinelRegistry key, e.g. 'passthrough', 'blocklist'). "
            "Sourced from tool_config.governance.sentinel.strategy."
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
# INFRA EVENT UNION
# ═══════════════════════════════════════════════════════════════════════════

InfraEvent = Annotated[
    StateWritten | VaultAccessed | FallbackFired | BudgetNotified | ToolGovernanceApplied,
    Field(discriminator="type")
]
"""Discriminated union of all infrastructure-layer events.

Mirrors the RunEvent union in history/events.py. The discriminator field
is 'type' — consistent with RunEvent and BusEnvelope conventions.

Deserialization:
    from xulcan.history.infra_events import InfraEvent
    from pydantic import TypeAdapter

    _adapter = TypeAdapter(InfraEvent)
    event: InfraEvent = _adapter.validate_python(raw_dict)

    match event:
        case FallbackFired(failed_provider=p):
            alert_on_provider_degradation(p, event)
        case BudgetNotified(current_tokens=t, limit=lim):
            update_cost_dashboard(event.run_id, t, lim)
        case ToolGovernanceApplied(tool_name=tool):
            write_to_compliance_ledger(event)

Publishing via the EventBus:
    Wrap in FirehosePayload before publishing — InfraEvents are domain events,
    not transport envelopes. The Kernel (or the emitting component) is
    responsible for constructing the FirehosePayload:

        FirehosePayload(
            run_id=event.run_id,
            event_type="fallback_fired",  # or a dedicated InfraEventType enum
            data=event.model_dump(),
        )
"""