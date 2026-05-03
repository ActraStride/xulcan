"""Base class and config contract for all HumanGate strategies.

The HumanGate answers one question when the Sentinel escalates:
    "How do we obtain human approval for this tool call?"

It receives the ToolCall and the escalation reason, and returns a
HumanGateResult — containing either APPROVED or REJECTED, along with optional
feedback that gets injected back into the agent's context.

The HumanGate is NOT the Sentinel. The Sentinel decides IF human approval
is needed. The HumanGate decides HOW to obtain it and what to do with the answer.

Deliberately does NOT inherit HumanGateStrategy (Protocol).
Duck typing handles structural compatibility.

NOTE: HumanGateDecision enum has been moved to xulcan.core.contracts to enable
cross-layer imports without circular dependencies.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from xulcan.core import ImmutableRecord, MachineID, SemanticText
from xulcan.governance.verdicts import HumanGateDecision  # ← Importado de contracts
from xulcan.protocol.tools import ToolCall

logger = logging.getLogger("xulcan.governance.human_gate")


# ═══════════════════════════════════════════════════════════════════════════
# RESULT
# ═══════════════════════════════════════════════════════════════════════════

class HumanGateResult(ImmutableRecord):
    """The full result from a HumanGate evaluation.

    Carries the decision plus optional feedback from the human operator.
    The feedback is injected into the agent's context as a system note.
    """
    decision: HumanGateDecision
    feedback: SemanticText | None = None


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

class BaseHumanGateConfig(ImmutableRecord):
    """Universal parameters for HumanGate strategies. Subclass to add specifics."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# BASE STRATEGY
# ═══════════════════════════════════════════════════════════════════════════

class BaseHumanGateStrategy(ABC):
    """Abstract base class for all HumanGate strategies.

    Template Method pattern:
        request_approval() handles standardized logging.
        _obtain_decision() is the pure mechanism each subclass implements.

    The Kernel calls request_approval() when transitioning to AWAITING_HUMAN.
    """

    ConfigSchema: type[BaseHumanGateConfig] = BaseHumanGateConfig

    def __init__(self, config: BaseHumanGateConfig):
        self.config = config

    async def request_approval(
        self,
        call: ToolCall,
        reason: SemanticText,
        run_id: MachineID,
    ) -> HumanGateResult:
        """Template method. Calls _obtain_decision() and handles logging.

        Args:
            call:    The tool call awaiting approval.
            reason:  Why the Sentinel escalated this call.
            run_id:  For log traceability.

        Returns:
            HumanGateResult containing the decision and optional feedback.
        """
        logger.info(
            f"[HumanGate] Run {run_id} — Requesting approval for "
            f"{call.name}() — Reason: {reason}"
        )

        result = await self._obtain_decision(call, reason, run_id)

        if result.decision == HumanGateDecision.APPROVED:
            logger.info(
                f"[HumanGate] Run {run_id} — APPROVED: {call.name}() "
                f"— Feedback: {result.feedback or 'none'}"
            )
        else:
            logger.warning(
                f"[HumanGate] Run {run_id} — REJECTED: {call.name}() "
                f"— Feedback: {result.feedback or 'none'}"
            )

        return result

    @abstractmethod
    async def _obtain_decision(
        self,
        call: ToolCall,
        reason: SemanticText,
        run_id: MachineID,
    ) -> HumanGateResult:
        """Mechanism to obtain human (or simulated) approval.

        Implementations can:
            - Block and wait for stdin input (TerminalHumanGate).
            - Send a webhook and poll for response (WebhookHumanGate).
            - Auto-approve for testing (AutoApproveHumanGate).
            - Auto-reject for safety testing (AutoRejectHumanGate).

        Args:
            call:    The tool call awaiting approval.
            reason:  Why the Sentinel escalated.
            run_id:  For correlation.

        Returns:
            HumanGateResult dictating the Kernel's next transition.
        """
        pass
