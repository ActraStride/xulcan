"""Base class and config contract for all Sentinel (policy enforcement) strategies.

The Sentinel answers one question before every tool execution:
    "Is this tool call permitted?"

It receives the ToolCall the model wants to execute and returns a SentinelResult:
    APPROVED  → execute the tool
    BLOCKED   → reject the tool, inject a refusal message into context
    ESCALATE  → pause and ask the HumanGate for approval

Deliberately does NOT inherit SentinelStrategy (Protocol).
Duck typing handles structural compatibility. Same philosophy as Context/Bursar.

NOTE: SentinelVerdict enum has been moved to xulcan.core.contracts to enable
cross-layer imports without circular dependencies.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from xulcan.core import ImmutableRecord, MachineID, SemanticText
from xulcan.governance.verdicts import SentinelVerdict  # ← Importado de contracts
from xulcan.protocol.tools import ToolCall

logger = logging.getLogger("xulcan.governance.sentinel")


# ═══════════════════════════════════════════════════════════════════════════
# RESULT (Richer than a plain verdict)
# ═══════════════════════════════════════════════════════════════════════════

class SentinelResult(ImmutableRecord):
    """The full result from a Sentinel evaluation.

    Carries the verdict plus an optional reason — useful for logging,
    injecting a refusal message back to the model, and providing context
    to the human reviewer via the HumanGate.
    """
    verdict: SentinelVerdict
    reason: SemanticText = ""


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

class BaseSentinelConfig(ImmutableRecord):
    """Universal parameters for Sentinel strategies. Subclass to add specifics."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# BASE STRATEGY
# ═══════════════════════════════════════════════════════════════════════════

class BaseSentinelStrategy(ABC):
    """Abstract base class for all Sentinel (policy enforcement) strategies.

    Template Method pattern:
        evaluate() handles standard logging based on the verdict.
        _check() is the pure algorithm each subclass implements.

    The Kernel calls evaluate() once per CHECKING_POLICY state.
    """

    ConfigSchema: type[BaseSentinelConfig] = BaseSentinelConfig

    def __init__(self, config: BaseSentinelConfig):
        self.config = config

    def evaluate(
        self,
        call: ToolCall,
        run_id: MachineID,
        loop_counter: int
    ) -> SentinelResult:
        """Template method. Calls _check() and handles logging.

        Args:
            call:         The tool call the model wants to execute.
            run_id:       For log traceability.
            loop_counter: Current reasoning loop number.

        Returns:
            SentinelResult containing the verdict and optional reason.
        """
        result = self._check(call)

        if result.verdict == SentinelVerdict.APPROVED:
            logger.debug(
                f"[Sentinel] Run {run_id} Loop {loop_counter} — "
                f"APPROVED: {call.name}()"
            )

        elif result.verdict == SentinelVerdict.BLOCKED:
            logger.warning(
                f"[Sentinel] Run {run_id} Loop {loop_counter} — "
                f"BLOCKED: {call.name}() — {result.reason}"
            )

        elif result.verdict == SentinelVerdict.ESCALATE:
            logger.info(
                f"[Sentinel] Run {run_id} Loop {loop_counter} — "
                f"ESCALATE: {call.name}() requires human approval — {result.reason}"
            )

        return result

    @abstractmethod
    def _check(self, call: ToolCall) -> SentinelResult:
        """Pure policy evaluation logic. No I/O, no side effects.

        Args:
            call: The tool call to evaluate.

        Returns:
            SentinelResult determining the next Kernel action.
        """
        pass
