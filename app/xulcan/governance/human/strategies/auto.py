"""AutoApprove HumanGate — automatically approves all escalations. Default strategy."""

from __future__ import annotations

from xulcan.core import MachineID
from xulcan.governance.human.base import (
    BaseHumanGateStrategy, BaseHumanGateConfig,
    HumanGateResult, HumanGateDecision
)
from xulcan.protocol.tools import ToolCall


class AutoApproveHumanGateStrategy(BaseHumanGateStrategy):
    """Approves all tool calls without human intervention.

    The default strategy. Semantically equivalent to 'no human gate'.
    Use for development, testing, and autonomous agents that don't require supervision.

    YAML:
        human_gate_strategy: "auto_approve"
        human_gate_params: {}
    """

    ConfigSchema = BaseHumanGateConfig

    async def _obtain_decision(
        self,
        call: ToolCall,
        reason: str,
        run_id: MachineID,
    ) -> HumanGateResult:
        
        return HumanGateResult(decision=HumanGateDecision.APPROVED)