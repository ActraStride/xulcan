# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN VERDICTS
# Vocabulary of the governance system. Not strategy implementations.
# Moved here from governance/*/base.py to break circular import chains and
# allow protocol/ and history/ layers to use them without governance imports.
# ═══════════════════════════════════════════════════════════════════════════

from enum import Enum

class SentinelVerdict(str, Enum):
    """The Sentinel's decision after evaluating a tool call.

    APPROVED:  Tool call is permitted. Execute normally.
    BLOCKED:   Tool call violates policy. Inject refusal into context.
               The model will see the refusal and can try another approach.
    ESCALATE:  Tool call requires human approval before execution.
               The Kernel transitions to SUSPENDED with SuspensionReason.HUMAN_GATE.
    """
    APPROVED = "approved"
    BLOCKED  = "blocked"
    ESCALATE = "escalate"


class BursarVerdict(str, Enum):
    """The Bursar's decision after evaluating resource consumption.

    APPROVED:  Budget is within limits. Proceed normally.
    WARN:      Budget threshold exceeded but strategy is SOFT_NOTIFY.
               Execution continues; event is emitted as BudgetNotified.
    HALT:      Budget hard cap exceeded. Kernel must stop the run.
               The Kernel raises BudgetExceededError on this verdict.
    """
    APPROVED = "approved"
    WARN     = "warn"
    HALT     = "halt"


class HumanGateDecision(str, Enum):
    """The HumanGate's decision after obtaining (or simulating) human input.

    APPROVED: Human approved the tool call. Proceed with execution.
    REJECTED: Human rejected the tool call. Inject feedback into context
              so the model can try a different approach.
    """
    APPROVED = "approved"
    REJECTED = "rejected"
