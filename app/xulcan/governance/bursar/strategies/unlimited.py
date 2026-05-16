from xulcan.governance.bursar.base import BaseBursarStrategy, BaseBursarConfig
from xulcan.governance.verdicts import BursarVerdict
from xulcan.core.economics import UsageStats


class UnlimitedBursarConfig(BaseBursarConfig):
    """Sin parámetros. Unlimited aprueba todo sin excepción."""
    pass


class UnlimitedBursarStrategy(BaseBursarStrategy):
    """Siempre aprueba. Equivalente a un stub estructural.

    Usa cuando:
        - No se declara budget en el Blueprint.
        - Desarrollo y testing sin preocupación por costos.

    YAML:
        governance:
          budget: unlimited
    """

    ConfigSchema = UnlimitedBursarConfig

    def _check(self, cumulative_usage: UsageStats) -> BursarVerdict:
        return BursarVerdict.APPROVED