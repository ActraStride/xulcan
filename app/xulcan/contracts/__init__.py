"""xulcan/contracts — módulo raíz de contratos transversales del framework.

Facade de re-exportación limpia. Todo consumidor importa desde aquí:

    from xulcan.contracts import (
        ModelSpec,
        StrategyConfig,
        BaseContextConfig,
        GovernanceConfig,
        ToolGovernanceConfig,
        BlueprintSnapshot,
    )

Dirección de dependencias (unidireccional, hacia abajo):
    contracts/ ← blueprint/
    contracts/ ← governance/
    contracts/ ← history/
    contracts/ ← kernel/
    contracts/ ← app/  (futura capa)

contracts/ depende solo de core/primitives.py.
Ningún módulo de dominio debe importar entre sí — todos apuntan hacia abajo
a contracts/ y core/, nunca lateralmente entre dominios.
"""

from xulcan.contracts.model import ModelSpec
from xulcan.contracts.strategy import StrategyConfig, BaseContextConfig
from xulcan.contracts.governance import GovernanceConfig, ToolGovernanceConfig
from xulcan.contracts.snapshot import BlueprintSnapshot

__all__ = [
    "ModelSpec",
    "StrategyConfig",
    "BaseContextConfig",
    "GovernanceConfig",
    "ToolGovernanceConfig",
    "BlueprintSnapshot",
]