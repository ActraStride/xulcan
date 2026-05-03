"""Suspension reasons for the Kernel FSM.

Centralized here to avoid circular imports and provide a single
source of truth for suspension reasons.
"""

from enum import Enum


class SuspensionReason(str, Enum):
    """Discriminator for why the Kernel entered SUSPENDED state.

    HUMAN_GATE:       A tool call is awaiting human approval via HumanGate.
                      The Kernel transitions back to EXECUTING_TOOL on approval
                      or to CHECKING_BUDGET on rejection.

    CHILD_FSM:        Reserved — a sub-agent FSM is running and the parent is
                      waiting for it to complete or yield.

    EXTERNAL_WEBHOOK: Execution is paused waiting for an external HTTP callback
                      (e.g. an async tool that triggers a background job).
    """
    HUMAN_GATE = "human_gate"
    CHILD_FSM = "child_fsm"
    EXTERNAL_WEBHOOK = "external_webhook"
