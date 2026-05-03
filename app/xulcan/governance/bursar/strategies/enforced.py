"""Enforced Bursar — real budget checking against BudgetConfig.

Respects BudgetStrategy semantics from core/economics.py:
    HARD_CAP    → HALT (raises BudgetExceededError in the Kernel)
    SOFT_NOTIFY → WARN (logs, continues)
"""

from __future__ import annotations

from pydantic import Field

from xulcan.governance.bursar.base import (
    BaseBursarStrategy, BaseBursarConfig, BursarVerdict
)

from xulcan.core import ImmutableRecord, FinitePositiveFloat, MachineID
from xulcan.core.economics import UsageStats, BudgetConfig, BudgetStrategy


class EnforcedBursarConfig(ImmutableRecord):
    # --- AÑADE ESTOS CAMPOS ---
    token_limit: int | None = Field(default=None, gt=0)
    time_limit_ms: FinitePositiveFloat | None = Field(default=None)


# xulcan/governance/bursar/strategies/enforced.py

class EnforcedBursarStrategy(BaseBursarStrategy):
    ConfigSchema = EnforcedBursarConfig
    def __init__(self, config: EnforcedBursarConfig):
        self.config = config

    def evaluate(
        self,
        cumulative_usage: UsageStats,
        run_id: MachineID,
        loop_counter: int,
    ) -> BursarVerdict:
        # Lógica pura usando la config interna
        if self.config.token_limit and cumulative_usage.total_tokens > self.config.token_limit:
            return BursarVerdict.HALT
            
        if self.config.time_limit_ms and cumulative_usage.latency_ms > self.config.time_limit_ms:
            return BursarVerdict.HALT

        return BursarVerdict.APPROVED
        
    def _check(self, cumulative_usage: UsageStats) -> BursarVerdict:
            # Usa self.config.token_limit en lugar de un objeto pasado
            if self.config.token_limit and cumulative_usage.total_tokens > self.config.token_limit:
                return BursarVerdict.HALT
            return BursarVerdict.APPROVED