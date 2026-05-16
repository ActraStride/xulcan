"""GovernanceConfig y ToolGovernanceConfig — contratos de gobernanza transversales.

Consumidos por blueprint/, governance/, kernel/, y la futura capa app/.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, AliasChoices

from xulcan.core.primitives import ImmutableRecord
from xulcan.contracts.strategy import StrategyConfig


class GovernanceConfig(ImmutableRecord):
    """Gobernanza a nivel Blueprint: solo budget.

    sentinel y human_gate fueron movidos a ToolGovernanceConfig porque
    son concerns per-tool, no per-agent. Aplicarlos al nivel Blueprint
    era demasiado grueso — diferentes tools tienen diferentes perfiles
    de riesgo y deben llevar su propia política independientemente.

    Alias de migración: 'bursar' es aceptado como alias de 'budget' para
    facilitar la migración del esquema plano anterior (bursar_strategy + bursar_params).
    El alias es solo para validación; la serialización siempre usa 'budget'.

    Attributes:
        budget: Estrategia de enforcement de budget. Default: 'unlimited'.
    """
    budget: StrategyConfig = Field(
        default_factory=lambda: StrategyConfig(strategy="unlimited"),
        validation_alias=AliasChoices("budget", "bursar"),
        description=(
            "Estrategia de enforcement de budget. "
            "Default: 'unlimited' (sin enforcement). "
            "Usa 'enforced' con token_limit / time_limit_ms para limitar consumo."
        )
    )


class ToolGovernanceConfig(ImmutableRecord):
    """Gobernanza per-tool: enforcement de política, aprobación humana, y constraints de ejecución.

    Vive en AgentToolConfig. Cada tool declara su gobernanza independientemente.
    Los defaults son intencionalmente seguros: sin policy checks, sin aprobación
    requerida, read-only, sin sandbox.

    Attributes:
        human_gate: Cómo obtener aprobación humana cuando el Sentinel escala.
        sentinel: Estrategia de enforcement de política para tool calls.
        side_effects: Perfil declarado de side-effects de este tool.
        sandbox: Si ejecutar este tool dentro de un entorno sandboxed.
    """
    human_gate: StrategyConfig = Field(
        default_factory=lambda: StrategyConfig(strategy="auto_approve"),
        description=(
            "Cómo obtener aprobación humana cuando el Sentinel escala. "
            "Default: 'auto_approve' (sin aprobación requerida). "
            "Usa 'terminal' o 'webhook' para flujos de aprobación reales."
        )
    )
    sentinel: StrategyConfig = Field(
        default_factory=lambda: StrategyConfig(strategy="passthrough"),
        description=(
            "Estrategia de enforcement de política para tool calls. "
            "Default: 'passthrough' (sin policy checks). "
            "Usa 'blocklist' o 'allowlist' para enforcement real."
        )
    )
    side_effects: Literal["read", "write"] = Field(
        default="read",
        description=(
            "Perfil declarado de side-effects de este tool. "
            "'read'  = no muta estado externo (idempotent safe). "
            "'write' = puede mutar estado externo (activa gobernanza más estricta). "
            "La declaración honesta es responsabilidad del operador."
        )
    )
    sandbox: bool = Field(
        default=False,
        description=(
            "Si ejecutar este tool dentro de un entorno sandboxed. "
            "Requiere un SandboxProvider configurado en app.py. "
            "Ignorado si no hay SandboxProvider registrado."
        )
    )  