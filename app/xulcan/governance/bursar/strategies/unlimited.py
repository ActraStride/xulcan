"""Unlimited Bursar — always approves. The default for development."""

from __future__ import annotations

from xulcan.governance.bursar.base import (
    BaseBursarStrategy, BaseBursarConfig, BursarVerdict
)
from xulcan.core.economics import UsageStats, BudgetConfig


class UnlimitedConfig(BaseBursarConfig):
    """No parameters. Unlimited strategy approves everything."""
    pass


class UnlimitedBursarStrategy(BaseBursarStrategy):
    """Always approves. Equivalent to a structural stub.

    Use for:
        - Development and testing.
        - Agents where cost is not a concern.
        - When no budget is declared in the Blueprint.

    YAML:
        bursar_strategy: "unlimited"
        bursar_params: {}
    """

    ConfigSchema = UnlimitedConfig

    def _check(self, cumulative_usage: UsageStats) -> BursarVerdict:
        # No importa cuánto gaste, esta estrategia siempre aprueba.
        return BursarVerdict.APPROVED