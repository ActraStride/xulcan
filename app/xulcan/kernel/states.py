
"""Finite State Machine (FSM) definitions for the Xulcan Kernel (DEFINITIVE VERSION).

This module defines the valid states and state transitions that govern
the agent execution lifecycle.

FIXED ISSUES:
    - Removed orphan AWAITING_HUMAN state (replaced by SUSPENDED)
    - Consistent state transitions matching definitive runtime.py
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType


# ═══════════════════════════════════════════════════════════════════════════
# STATE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

class KernelState(str, Enum):
    """Valid states in the Kernel execution FSM.

    Each state represents a distinct phase in the agent lifecycle.
    """

    # Initialization
    IDLE = "idle"
    CREATED = "created"

    # Hydration (Event Replay)
    HYDRATING = "hydrating"
    HYDRATED = "hydrated"

    # Governance (Budget)
    CHECKING_BUDGET = "checking_budget"

    # Context Management
    PREPARING_CONTEXT = "preparing_context"
    COMPACTING_CONTEXT = "compacting_context"

    # LLM Inference
    CALLING_MODEL = "calling_model"
    PROCESSING_RESPONSE = "processing_response"

    # Tool Execution Path
    PARSING_TOOL_ARGS = "parsing_tool_args"
    CHECKING_POLICY = "checking_policy"

    # Suspension (external pause — human gate, webhook, future child FSM)
    SUSPENDED = "suspended"

    # Tool Execution
    EXECUTING_TOOL = "executing_tool"

    # Error Recovery with Retry
    RETRYING = "retrying"
    HANDLING_ERROR = "handling_error"

    # Terminal States
    COMPLETED = "completed"
    FAILED = "failed"


# ═══════════════════════════════════════════════════════════════════════════
# TRANSITION GRAPH
# ═══════════════════════════════════════════════════════════════════════════

_VALID_TRANSITIONS_DICT: dict[KernelState, frozenset[KernelState]] = {
    # From IDLE
    KernelState.IDLE: frozenset({
        KernelState.CREATED,
    }),

    # From CREATED
    KernelState.CREATED: frozenset({
        KernelState.HYDRATING,
        KernelState.FAILED,
    }),

    # From HYDRATING
    KernelState.HYDRATING: frozenset({
        KernelState.HYDRATED,
        KernelState.FAILED,
    }),

    # From HYDRATED
    KernelState.HYDRATED: frozenset({
        KernelState.CHECKING_BUDGET,
    }),

    # From CHECKING_BUDGET
    KernelState.CHECKING_BUDGET: frozenset({
        KernelState.PREPARING_CONTEXT,
        KernelState.FAILED,
    }),

    # From PREPARING_CONTEXT
    KernelState.PREPARING_CONTEXT: frozenset({
        KernelState.COMPACTING_CONTEXT,
        KernelState.FAILED,
    }),

    # From COMPACTING_CONTEXT
    KernelState.COMPACTING_CONTEXT: frozenset({
        KernelState.CALLING_MODEL,
        KernelState.FAILED,
    }),

    # From CALLING_MODEL
    KernelState.CALLING_MODEL: frozenset({
        KernelState.PROCESSING_RESPONSE,
        KernelState.RETRYING,
        KernelState.HANDLING_ERROR,
    }),

    # From RETRYING
    KernelState.RETRYING: frozenset({
        KernelState.CALLING_MODEL,
        KernelState.HANDLING_ERROR,
    }),

    # From PROCESSING_RESPONSE
    KernelState.PROCESSING_RESPONSE: frozenset({
        KernelState.COMPLETED,
        KernelState.PARSING_TOOL_ARGS,
        KernelState.HANDLING_ERROR,
    }),

    # From PARSING_TOOL_ARGS
    KernelState.PARSING_TOOL_ARGS: frozenset({
        KernelState.CHECKING_POLICY,
        KernelState.HANDLING_ERROR,
    }),

    # From CHECKING_POLICY
    KernelState.CHECKING_POLICY: frozenset({
        KernelState.EXECUTING_TOOL,
        KernelState.SUSPENDED,
        KernelState.CHECKING_BUDGET,
        KernelState.HANDLING_ERROR,
    }),

    # From SUSPENDED
    KernelState.SUSPENDED: frozenset({
        KernelState.EXECUTING_TOOL,
        KernelState.CHECKING_BUDGET,
        KernelState.HANDLING_ERROR,
    }),

    # From EXECUTING_TOOL
    KernelState.EXECUTING_TOOL: frozenset({
        KernelState.CHECKING_BUDGET,
        KernelState.HANDLING_ERROR,
    }),

    # From HANDLING_ERROR
    KernelState.HANDLING_ERROR: frozenset({
        KernelState.RETRYING,
        KernelState.FAILED,
    }),

    # Terminal states
    KernelState.COMPLETED: frozenset(),
    KernelState.FAILED: frozenset(),
}

# Automatically inject FAILED as valid transition for all non-terminal states
for state, valid_targets in list(_VALID_TRANSITIONS_DICT.items()):
    if state not in (KernelState.COMPLETED, KernelState.FAILED):
        _VALID_TRANSITIONS_DICT[state] = valid_targets | frozenset({KernelState.FAILED})

# Public Immutable Proxy
VALID_TRANSITIONS = MappingProxyType(_VALID_TRANSITIONS_DICT)


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

class InvalidTransitionError(RuntimeError):
    """Raised when attempting an illegal state transition."""

    def __init__(
        self,
        from_state: KernelState,
        to_state: KernelState,
        valid_transitions: frozenset[KernelState],
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.valid_transitions = valid_transitions

        valid_str = ", ".join(s.value for s in valid_transitions)
        super().__init__(
            f"Invalid transition: {from_state.value} → {to_state.value}. "
            f"Valid transitions from {from_state.value}: {{{valid_str}}}"
        )


def validate_transition(from_state: KernelState, to_state: KernelState) -> None:
    """Validates that a state transition is legal according to the FSM."""
    valid_targets = VALID_TRANSITIONS.get(from_state, frozenset())

    if to_state not in valid_targets:
        raise InvalidTransitionError(from_state, to_state, valid_targets)


def is_terminal_state(state: KernelState) -> bool:
    """Checks if a state is terminal (no outgoing transitions)."""
    return len(VALID_TRANSITIONS.get(state, frozenset())) == 0


def get_valid_transitions(state: KernelState) -> set[KernelState]:
    """Returns the set of valid target states from the given state."""
    return set(VALID_TRANSITIONS.get(state, frozenset()))
