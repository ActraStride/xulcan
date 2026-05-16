"""StrategyConfig y BaseContextConfig — contratos de estrategia transversales.

Ambos tipos son consumidos por blueprint/, governance/, context/, y kernel/.
Deben vivir en contracts/ para evitar inversión de dependencias.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from xulcan.core.primitives import ImmutableRecord, MachineID, JsonDict


class StrategyConfig(ImmutableRecord):
    """Referencia tipada a una estrategia con sus parámetros de inicialización.

    Soporta tres formas sintácticas para ergonomía YAML:

    1. String shorthand (estrategia sin params):
        budget: unlimited
        → StrategyConfig(strategy="unlimited", params={})

    2. Dict anidado shorthand (estrategia con params):
        budget:
          enforced:
            token_limit: 50000
        → StrategyConfig(strategy="enforced", params={"token_limit": 50000})

    3. Forma canónica explícita (siempre aceptada):
        budget:
          strategy: enforced
          params:
            token_limit: 50000
        → StrategyConfig(strategy="enforced", params={"token_limit": 50000})

    Attributes:
        strategy: Clave de la estrategia (mapea al Registry correspondiente).
        params: Parámetros enviados al ConfigSchema del constructor de la estrategia.
    """
    strategy: MachineID = Field(
        description="Clave de la estrategia (mapea al Registry correspondiente)."
    )
    params: JsonDict = Field(
        default_factory=dict,
        description=(
            "Parámetros enviados al ConfigSchema del constructor de la estrategia. "
            "Dict vacío = la estrategia usa todos sus defaults."
        )
    )

    @model_validator(mode='before')
    @classmethod
    def parse_fluid(cls, value: Any) -> Any:
        """Normaliza sintaxis YAML fluida a dict canónico StrategyConfig.

        Raises:
            ValueError: Si se provee un dict ambiguo (más de una clave,
                sin clave 'strategy').
        """
        if isinstance(value, str):
            return {"strategy": value.strip(), "params": {}}

        if isinstance(value, dict):
            if "strategy" in value:
                return value
            if len(value) == 1:
                strategy_name, params = next(iter(value.items()))
                return {"strategy": strategy_name, "params": params or {}}
            raise ValueError(
                f"StrategyConfig dict ambiguo: {value!r}. "
                "Usa {'strategy': name, 'params': {...}} (canónico) "
                "o {strategy_name: params_dict} (shorthand) — no ambos."
            )

        return value


class BaseContextConfig(ImmutableRecord):
    """Parámetros base universales para todas las estrategias de contexto.

    Vive en contracts/ para que la capa blueprint pueda importar la base
    de configuración sin jalar toda la maquinaria del context engine
    (ABC BaseContextStrategy, tipos UnifiedMessage, rendering Jinja2, etc.).

    El ABC de estrategia (BaseContextStrategy) permanece en context/base.py.
    Las configs concretas subclasean esto y añaden sus params específicos:

        class SlidingWindowConfig(BaseContextConfig):
            max_messages: int = 10
    """
    pass