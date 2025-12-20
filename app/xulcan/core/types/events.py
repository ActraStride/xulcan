"""Defines runtime execution event types (the "History" dimension).

This module contains types for tracking agent execution through an immutable,
append-only event log (Event Sourcing / "The Tape"). Events enable time travel,
replay, forking, and complete observability of agent behavior.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Literal
from pydantic import Field, field_validator

from .base import CanonicalModel


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL ENUMS (Not exported in __init__.py)
# ═══════════════════════════════════════════════════════════════════════════

class _RunStatus(str, Enum):
    """Internal enum for run status validation.
    
    External APIs use string literals for stability. This enum is used
    internally for state machine validation only.
    """
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class _EventType(str, Enum):
    """Internal enum for event type validation.
    
    External APIs use string literals for stability. This enum is used
    internally for event routing and validation only.
    """
    # Run Lifecycle
    RUN_CREATED = "run_created"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    
    # Execution Steps
    STEP_STARTED = "step_started"
    
    # LLM Interactions
    LLM_REQUEST_SENT = "llm_request_sent"
    LLM_RESPONSE_RECEIVED = "llm_response_received"
    
    # Tool Execution
    TOOL_CALL_DETECTED = "tool_call_detected"
    TOOL_EXECUTION_STARTED = "tool_execution_started"
    TOOL_OUTPUT_RECEIVED = "tool_output_received"
    
    # Human-in-the-Loop
    HUMAN_INTERVENTION_REQUIRED = "human_intervention_required"
    HUMAN_APPROVED = "human_approved"


# ═══════════════════════════════════════════════════════════════════════════
# EVENT TYPES
# ═══════════════════════════════════════════════════════════════════════════

class RunEvent(CanonicalModel):
    """Represents a single immutable event in an agent execution timeline.
    
    This is the History dimension of Xulcan's Trinity. Events form an
    append-only log that enables:
    - Time travel (replay from any point)
    - Forking (create alternate timelines)
    - Debugging (see exactly what happened when)
    - Auditing (immutable compliance trail)
    
    Design Philosophy:
        - Events are NEVER mutated or deleted
        - Each event captures a discrete moment in time
        - The full history is the source of truth
        - State is derived from event replay
    
    Attributes:
        id: Unique event identifier (UUID v4).
        run_id: Identifier of the execution run this event belongs to.
        timestamp: When this event occurred (UTC).
        type: What kind of event this is.
        step_index: Which step in the execution this event corresponds to.
        payload: Event-specific data (structure depends on type).
    
    Example:
        >>> # Run creation event
        >>> event = RunEvent(
        ...     run_id="run_abc123",
        ...     type="run_created",
        ...     step_index=0,
        ...     payload={
        ...         "agent_id": "weather-assistant",
        ...         "user_input": "What's the weather in Paris?"
        ...     }
        ... )
        >>> 
        >>> # LLM response event
        >>> event = RunEvent(
        ...     run_id="run_abc123",
        ...     type="llm_response_received",
        ...     step_index=1,
        ...     payload={
        ...         "content": "Let me search for the weather.",
        ...         "tool_calls": [{"name": "web_search", ...}],
        ...         "usage": {"input_tokens": 42, "output_tokens": 18}
        ...     }
        ... )
    """
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event identifier (UUID v4)"
    )
    
    run_id: str = Field(
        min_length=1,
        description="Identifier of the execution run this event belongs to"
    )
    
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this event occurred (always UTC)"
    )
    
    type: Literal[
        # Run Lifecycle
        "run_created",
        "run_completed",
        "run_failed",
        # Execution Steps
        "step_started",
        # LLM Interactions
        "llm_request_sent",
        "llm_response_received",
        # Tool Execution
        "tool_call_detected",
        "tool_execution_started",
        "tool_output_received",
        # Human-in-the-Loop
        "human_intervention_required",
        "human_approved",
    ] = Field(
        description="Event type discriminator"
    )
    
    step_index: int = Field(
        ge=0,
        description="Which step in the execution this event corresponds to"
    )
    
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data (structure depends on type)"
    )

    @field_validator('run_id')
    @classmethod
    def validate_run_id(cls, v: str) -> str:
        """Ensure run_id is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("run_id cannot be empty or whitespace")
        return v.strip()

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp_is_utc(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware and in UTC.
        
        Event sourcing requires consistent timezone handling for replay.
        """
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (use timezone.utc)")
        
        # Convert to UTC if it's not already
        if v.tzinfo != timezone.utc:
            v = v.astimezone(timezone.utc)
        
        return v

    @property
    def is_terminal_event(self) -> bool:
        """Check if this event marks the end of a run.
        
        Returns:
            True if this is a run_completed or run_failed event.
        
        Example:
            >>> event = RunEvent(run_id="123", type="run_completed", step_index=5)
            >>> event.is_terminal_event
            True
        """
        return self.type in ("run_completed", "run_failed")

    @property
    def is_llm_event(self) -> bool:
        """Check if this event relates to LLM interaction.
        
        Returns:
            True if this is an llm_request_sent or llm_response_received event.
        """
        return self.type in ("llm_request_sent", "llm_response_received")

    @property
    def is_tool_event(self) -> bool:
        """Check if this event relates to tool execution.
        
        Returns:
            True if this is any tool-related event.
        """
        return self.type in (
            "tool_call_detected",
            "tool_execution_started",
            "tool_output_received"
        )

    @property
    def is_human_event(self) -> bool:
        """Check if this event relates to human intervention.
        
        Returns:
            True if this is a human_intervention_required or human_approved event.
        """
        return self.type in (
            "human_intervention_required",
            "human_approved"
        )

    def __repr__(self) -> str:
        """Provide a concise string representation for logging.
        
        Example:
            >>> event = RunEvent(run_id="run_abc123", type="step_started", step_index=2)
            >>> repr(event)
            'RunEvent(type=step_started, run=run_abc1..., step=2)'
        """
        run_id_short = self.run_id[:8] + "..." if len(self.run_id) > 8 else self.run_id
        return (
            f"RunEvent(type={self.type}, "
            f"run={run_id_short}, "
            f"step={self.step_index})"
        )