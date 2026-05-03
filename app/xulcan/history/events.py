"""Defines runtime execution event types (the "History" dimension).

This module implements the "Event Sourcing" pattern using Strict Polymorphism.
Instead of a generic JSON payload, each event type is a distinct class schema.
This guarantees that if the event type is 'run_failed', the consumer KNOWS
there is an 'error_type' field available.

The event ledger is the single source of truth for:
- Auditing and compliance
- Debugging and observability
- Replay and time-travel debugging
- Usage tracking and cost attribution

Events are immutable and append-only. They capture WHAT HAPPENED, not what
should happen next (that's the Kernel's job).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Annotated
from enum import Enum
from pydantic import Field, field_validator

from xulcan.core.primitives import (
    ImmutableRecord, 
    MachineID,
    SemanticText,
    ExternalID,
    JsonDict,
    SemanticVersion
)
from xulcan.blueprint.types import BlueprintSnapshot, StrategyConfig
from xulcan.core.economics import BudgetConfig, UsageStats
from xulcan.protocol.message import UnifiedMessage
from xulcan.protocol.tools import ToolCall


# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN ENUMERATIONS
# ═══════════════════════════════════════════════════════════════════════════

class EventType(str, Enum):
    # Lifecycle
    RUN_CREATED = "run_created"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    
    # Flow
    STEP_STARTED = "step_started"
    
    # Inference
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
    MODEL_FALLBACK = "model_fallback"
    
    # Tooling
    TOOL_EXECUTION = "tool_execution"
    TOOL_OUTPUT = "tool_output"
    
    # Governance
    POLICY_VIOLATION = "policy_violation"
    HUMAN_INTERVENTION_REQUIRED = "human_intervention_required"
    HUMAN_INTERVENTION_RESULT = "human_intervention_result"


class StepType(str, Enum):
    INFERENCE = "inference"
    TOOL_EXECUTION = "tool_execution"
    LIFECYCLE = "lifecycle"


class RunStatus(str, Enum):
    """High-level status for the Ledger Projection (RunSnapshot).
    Differs from KernelState (FSM) which is granular and ephemeral.
    """
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"    # Awaiting human intervention
    COMPLETED = "completed"
    FAILED = "failed"


# ═══════════════════════════════════════════════════════════════════════════
# BASE EVENT (ABSTRACT)
# ═══════════════════════════════════════════════════════════════════════════

class BaseRunEvent(ImmutableRecord):
    """Abstract base class for all execution events.
    
    Contains the shared metadata required for auditing, sequencing, and tracing.
    Does not contain payload data (defined in subclasses).
    
    Design Philosophy:
        - Events are immutable facts about the past.
        - Timestamps are always UTC and timezone-aware.
        - step_index provides a logical clock for ordering.
        - metadata enables distributed tracing.
    """
    type: EventType

    id: MachineID = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event identifier (UUID v4)."
    )
    
    run_id: MachineID = Field(
        description="Trace ID linking this event to a specific execution run."
    )
    
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this event occurred (always UTC)."
    )

    sequence_number: int = Field(
        ge=1,
        description="Absolute monotonic counter for this event within the run (1, 2, 3...). Vital for deterministic replay."
    )
    
    step_index: int = Field(
        ge=0,
        description="Logical clock / Sequence number within the run."
    )
    
    metadata: JsonDict = Field(
        default_factory=dict,
        description="Tracing info (user_id, correlation_id, app_version, etc.)."
    )

    @field_validator('timestamp', mode="after")
    @classmethod
    def validate_timestamp_is_utc(cls, value: datetime) -> datetime:
        """Ensure timestamp is timezone-aware and normalized to UTC."""
        if value.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware.")
        if value.tzinfo != timezone.utc:
            value = value.astimezone(timezone.utc)
        return value


# ═══════════════════════════════════════════════════════════════════════════
# LIFECYCLE EVENTS (Run Boundary)
# ═══════════════════════════════════════════════════════════════════════════

class RunCreated(BaseRunEvent):
    """The Big Bang. Fired when a new agent run is initialized."""
    type: Literal[EventType.RUN_CREATED] = EventType.RUN_CREATED
    
    agent_id: MachineID = Field(
        description="👤 Quién: Identifier of the user or memory instance running the agent."
    )
    
    blueprint_id: MachineID = Field(
        description="🧠 Qué: The ID of the AgentBlueprint (DNA) used for this run."
    )

    blueprint_snapshot: BlueprintSnapshot = Field(
        description=(
            "📸 Snapshot: Immutable, reproducible subset of the blueprint at the exact "
            "moment of execution. Stored so the Ledger can replay any historical run "
            "without requiring the original blueprint to still exist in its original form."
        )
    )
    
    agent_version: SemanticVersion = Field(
        description="Semantic version of the agent blueprint."
    )
    
    user_input: list[UnifiedMessage] = Field(
        min_length=1,
        description="Initial user messages that triggered this run."
    )
    
    initial_budget: StrategyConfig | None = Field(
        default=None,
        description="Budget strategy config at time of creation."
    )

class RunCompleted(BaseRunEvent):
    """Fired when the run finishes successfully.
    
    This is the terminal success state. After this event, no more events
    should be appended to the run's ledger.
    """
    type: Literal[EventType.RUN_COMPLETED] = EventType.RUN_COMPLETED
    
    final_response: UnifiedMessage | None = Field(
        default=None,
        description="The agent's final output (may be None for no-response runs)."
    )
    
    total_usage: UsageStats = Field(
        description="Cumulative tokens, cost, and latency across all LLM calls."
    )


class RunFailed(BaseRunEvent):
    """Fired when the run crashes or encounters a fatal error.
    
    This is the terminal failure state. Contains diagnostic information
    for debugging and alerting.
    """
    type: Literal[EventType.RUN_FAILED] = EventType.RUN_FAILED
    
    error_type: MachineID = Field(
        description="Error classification (timeout, validation_error, etc.)."
    )
    
    error_message: SemanticText = Field(
        min_length=1,
        description="Human-readable error description."
    )
    
    traceback: SemanticText | None = Field(
        default=None,
        description="Python traceback for debugging (omitted in production)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# FLOW EVENTS (Kernel State Transitions)
# ═══════════════════════════════════════════════════════════════════════════

class StepStarted(BaseRunEvent):
    """Marks the beginning of a processing cycle in the agent loop.
    
    This event is critical for the "Fold" operation (H2 in Trinity) to know
    when to clear temporary contexts and reset state for the next iteration.
    """
    type: Literal[EventType.STEP_STARTED] = EventType.STEP_STARTED
    
    step_type: StepType = Field(
        description="Classification of this processing step."
    )


# ═══════════════════════════════════════════════════════════════════════════
# INFERENCE EVENTS (LLM Interactions)
# ═══════════════════════════════════════════════════════════════════════════

class ModelRequest(BaseRunEvent):
    """Fired just before sending the payload to the LLM provider.
    
    Captures the exact input that was sent, enabling perfect reproducibility
    and debugging of model behavior.
    """
    type: Literal[EventType.MODEL_REQUEST] = EventType.MODEL_REQUEST
    
    provider: ExternalID = Field(
        description="LLM provider name (openai, anthropic, google)."
    )
    
    model: ExternalID = Field(
        description="Specific model identifier (e.g., gpt-4, claude-sonnet-4)."
    )
    
    prompt_messages: list[UnifiedMessage] = Field(
        min_length=1,
        description="The conversation history sent to the model."
    )
    
    parameters: JsonDict = Field(
        default_factory=dict,
        description=(
            "Sampling parameters forwarded to the provider API "
            "(temperature, top_p, max_tokens, stop_sequences, etc.). "
            "Intentionally typed as JsonDict — these are provider-level params, "
            "not Blueprint-level params. The set of valid keys varies per provider "
            "and is not bounded by the Xulcan schema."
        )
    )


class ModelResponse(BaseRunEvent):
    """Fired when the LLM responds successfully.
    
    Captures the model's output and performance metrics.
    Note: Latency is tracked internally within the 'usage' field.
    """
    type: Literal[EventType.MODEL_RESPONSE] = EventType.MODEL_RESPONSE
    
    message: UnifiedMessage = Field(
        description="The model's output message (may contain tool calls)."
    )
    
    usage: UsageStats = Field(
        description="Token counts and timing for this specific request."
    )
    
    provider_id: ExternalID | None = Field(
        default=None,
        description="Provider-specific request ID for support queries."
    )

class ModelFallback(BaseRunEvent):
    """Fired when the primary LLM fails and the executor switches to a fallback."""
    type: Literal[EventType.MODEL_FALLBACK] = EventType.MODEL_FALLBACK

    failed_provider: MachineID = Field(
        description="Provider key that failed (maps to ProviderRegistry key)."
    )
    reason: SemanticText = Field(
        description="Human-readable explanation of why the primary provider failed."
    )
    next_provider: MachineID = Field(
        description="Provider key of the fallback now in use."
    )
    model_name: ExternalID = Field(
        description="Model name on the fallback provider (as the provider expects it in its API)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# TOOL EVENTS (Function Execution)
# ═══════════════════════════════════════════════════════════════════════════

class ToolExecution(BaseRunEvent):
    """Fired when the Kernel decides to execute a tool.
    
    Captures the decision point before actual execution. If the tool crashes,
    there will be a ToolExecution but no matching ToolOutput.
    """
    type: Literal[EventType.TOOL_EXECUTION] = EventType.TOOL_EXECUTION
    
    tool_call: ToolCall = Field(
        description="The parsed tool call from the model's response."
    )
    
    tool_input: JsonDict = Field(
        default_factory=dict,
        description="The actual arguments passed to the tool function."
    )


class ToolOutput(BaseRunEvent):
    """Fired when a tool finishes execution (success or failure).
    
    Contains the raw output from the tool. The Kernel decides how to
    serialize this into a message for the model.
    """
    type: Literal[EventType.TOOL_OUTPUT] = EventType.TOOL_OUTPUT
    
    tool_call_id: ExternalID = Field(
        description="Links this output to the corresponding ToolExecution."
    )
    
    tool_name: MachineID = Field(
        description="Which tool produced this output."
    )
    
    output: SemanticText = Field(
        description="Serialized result (JSON, text, or error message)."
    )
    
    is_error: bool = Field(
        default=False,
        description="Whether this output represents a tool execution failure."
    )


# ═══════════════════════════════════════════════════════════════════════════
# GOVERNANCE & SAFETY EVENTS (Policy Enforcement)
# ═══════════════════════════════════════════════════════════════════════════

class PolicyViolation(BaseRunEvent):
    """Fired when the Kernel blocks an action due to policy constraints.
    
    This is the enforcement point for safety guardrails. The model is NOT
    allowed to execute the violating tool, and this event explains why.
    """
    type: Literal[EventType.POLICY_VIOLATION] = EventType.POLICY_VIOLATION
    
    violating_tool: MachineID = Field(
        description="Which tool call triggered the policy violation."
    )
    
    reason: SemanticText = Field(
        min_length=1,
        description="Human-readable explanation of why this was blocked."
    )
    
    policy_id: MachineID | None = Field(
        default=None,
        description="Identifier of the specific policy that was violated."
    )


class HumanInterventionRequired(BaseRunEvent):
    """Fired when the Kernel pauses execution and requests human approval.
    
    The run enters a suspended state until a human operator reviews the
    context and provides a decision via HumanInterventionResult.
    """
    type: Literal[EventType.HUMAN_INTERVENTION_REQUIRED] = EventType.HUMAN_INTERVENTION_REQUIRED
    
    reason: SemanticText = Field(
        min_length=1,
        description="Why human approval is needed (destructive_action, etc.)."
    )
    
    data_context: JsonDict = Field(
        default_factory=dict,
        description="Context data for the human to review before deciding."
    )


class HumanInterventionResult(BaseRunEvent):
    """Fired when a human operator responds to a HumanInterventionRequired event.
    
    Contains the human's decision (approve/reject) and optional feedback that
    gets injected back into the agent's context.
    """
    type: Literal[EventType.HUMAN_INTERVENTION_RESULT] = EventType.HUMAN_INTERVENTION_RESULT
    
    approved: bool = Field(
        description="Whether the human approved the pending action."
    )
    
    feedback: SemanticText | None = Field(
        default=None,
        description="Optional explanation or guidance from the human operator."
    )


# ═══════════════════════════════════════════════════════════════════════════
# THE UNION (POLYMORPHIC CONTAINER)
# ═══════════════════════════════════════════════════════════════════════════

RunEvent = Annotated[
    RunCreated | RunCompleted | RunFailed |
    StepStarted |
    ModelRequest | ModelResponse | ModelFallback |
    ToolExecution | ToolOutput |
    PolicyViolation | HumanInterventionRequired | HumanInterventionResult,
    Field(discriminator='type')
]


# ═══════════════════════════════════════════════════════════════════════════
# READ MODELS (PROJECTIONS)
# ═══════════════════════════════════════════════════════════════════════════

class RunSummary(ImmutableRecord):
    """A read-only projection of the agent's current state (The 'Fold' result).
    
    This replaces the abstract 'StateView'. It is a concrete DTO that
    can be serialized to JSON and sent over APIs.
    """
    run_id: MachineID
    
    status: RunStatus = Field(
        description="High-level lifecycle status (for UI/API)."
    )
    
    step_count: int = Field(
        ge=0,
        description="Current logical clock / sequence number."
    )
    
    created_at: datetime = Field(
        description="When the run started."
    )
    
    updated_at: datetime = Field(
        description="Timestamp of the last event."
    )
    
    last_event: RunEvent | None = Field(
        default=None,
        description="The most recent event appended to the ledger."
    )
    
    @property
    def is_terminal(self) -> bool:
        """True if the run has reached a final state."""
        return self.status in (RunStatus.COMPLETED, RunStatus.FAILED)

"""
═══════════════════════════════════════════════════════════════════════════
USAGE EXAMPLE: Pattern Matching with Strict Polymorphism
═══════════════════════════════════════════════════════════════════════════

    def process_event(event: RunEvent) -> None:
        # Python 3.10+ Pattern Matching works perfectly!
        match event:
            case RunFailed(error_type=err, error_message=msg):
                log.error(f"Run failed: {err} - {msg}")
                alert_ops_team(event)
            
            case ModelResponse(usage=stats):
                lat = stats.latency_ms
                metrics.record_llm_call(stats, lat)
                log.info(f"LLM call: {stats.total_tokens} tokens in {lat}ms")
            
            case PolicyViolation(violating_tool=tool, reason=reason):
                log.warning(f"Blocked {tool}: {reason}")
                notify_security_team(event)
            
            case HumanInterventionRequired(reason=reason):
                log.info(f"Human approval needed: {reason}")
                enqueue_for_review(event)
            
            case ToolOutput(tool_name=name, is_error=True):
                log.error(f"Tool {name} failed")
                retry_with_fallback(event)
            
            case _:
                log.debug(f"Event: {event.type}")
"""