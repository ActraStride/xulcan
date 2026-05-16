"""Base class and config contract for all Bursar (budget governance) strategies.

The Bursar answers one question before every reasoning loop:
    "Do we have the resources to continue?"

NOTE: In V2.0, strategies are AUTONOMOUS. They receive their limits 
(token_limit, etc.) via self.config during instantiation, not as 
arguments in every call.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from xulcan.core import MachineID, ImmutableRecord
from xulcan.core.economics import UsageStats
from xulcan.governance.verdicts import BursarVerdict

logger = logging.getLogger("xulcan.governance.bursar")


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

class BaseBursarConfig(ImmutableRecord):
    """Universal parameters for Bursar strategies. Subclass to add specifics."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# BASE STRATEGY
# ═══════════════════════════════════════════════════════════════════════════

class BaseBursarStrategy(ABC):
    """Abstract base class for all Bursar (budget governance) strategies.

    Template Method pattern:
        evaluate() handles logging and orchestration.
        _check() is the pure algorithm each subclass implements.
    """

    ConfigSchema: type[BaseBursarConfig] = BaseBursarConfig

    def __init__(self, config: BaseBursarConfig):
        self.config = config

    def evaluate(
        self,
        cumulative_usage: UsageStats,
        run_id: MachineID,
        loop_counter: int
    ) -> BursarVerdict:
        """Template method. Calls _check() and handles standardized logging.
        
        ✅ REMOVED: budget parameter. The strategy uses self.config.
        """
        verdict = self._check(cumulative_usage)

        if verdict == BursarVerdict.APPROVED:
            logger.debug(
                f"[Bursar] Run {run_id} Loop {loop_counter} — APPROVED "
                f"(tokens: {cumulative_usage.total_tokens}, "
                f"latency: {cumulative_usage.latency_ms}ms)"
            )

        elif verdict == BursarVerdict.WARN:
            logger.warning(
                f"[Bursar] Run {run_id} Loop {loop_counter} — BUDGET WARNING "
                f"(tokens: {cumulative_usage.total_tokens}, "
                f"latency: {cumulative_usage.latency_ms}ms) — "
                f"Soft limit exceeded."
            )

        elif verdict == BursarVerdict.HALT:
            logger.error(
                f"[Bursar] Run {run_id} Loop {loop_counter} — BUDGET HALT "
                f"(tokens: {cumulative_usage.total_tokens}, "
                f"latency: {cumulative_usage.latency_ms}ms) — "
                f"Hard cap exceeded. Stopping run."
            )

        if verdict == BursarVerdict.HALT:
            # La estrategia levanta el error con los datos que solo ella conoce.
            # El Kernel hace re-raise sin necesitar inspeccionar BursarConfig.
            self._raise_halt(cumulative_usage)

        return verdict

    def _raise_halt(self, cumulative_usage: UsageStats) -> None:
        """Levanta BursarHaltError con contexto de límite.
        
        Las subclases con límites específicos pueden sobreescribir esto
        para proveer limit y limit_type precisos. La implementación base
        usa el consumo actual como proxy (para UnlimitedBursarStrategy
        esto nunca se llama).
        """
        from xulcan.governance.errors import BursarHaltError
        raise BursarHaltError(
            "Bursar halted the run.",
            current_usage=float(cumulative_usage.total_tokens),
            limit=0.0,
            limit_type="unknown",
        )

    @abstractmethod
    def _check(
        self,
        cumulative_usage: UsageStats
    ) -> BursarVerdict:
        """Pure logic. Each strategy implementation must define this.
        
        ✅ REMOVED: budget parameter.
        """
        pass