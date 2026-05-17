"""BlueprintSnapshot — subconjunto inmutable y reproducible de un AgentBlueprint.

Viaja con un run durante todo su ciclo de vida. Almacenado en eventos RunCreated
para que el Ledger pueda replay cualquier run histórico sin requerir que el
Blueprint original siga existiendo en su forma o versión original.
"""

from __future__ import annotations

from pydantic import Field

from xulcan.core.primitives import ImmutableRecord, MachineID, SemanticVersion
from xulcan.contracts.model import ModelSpec
from xulcan.contracts.governance import GovernanceConfig


class BlueprintSnapshot(ImmutableRecord):
    """Subconjunto inmutable y reproducible de un AgentBlueprint.

    Rationale de selección de subset:
        Incluido — campos que afectan la reproducibilidad del comportamiento
        cognitivo del agente: elección de modelo, gobernanza de budget,
        estrategia de contexto.

        Excluido — concerns de infraestructura que varían por entorno de
        deployment y no afectan qué piensa o decide el agente:
            - timeout_seconds (operacional, no cognitivo)
            - tools (almacenados separadamente via RunCreated.tool_names)
            - system_prompt (almacenado en RunCreated.system_prompt_hash)
            - api_key, db_url, etc. (nunca en el Blueprint por diseño)

    Attributes:
        id: Identificador del blueprint del agente al momento del run.
        version: Versión semántica del blueprint al momento del run.
        model: Spec del modelo LLM al momento del run (provider + name + params).
        governance: Config de gobernanza de budget al momento del run.
        context_strategy: Clave de la estrategia de contexto al momento del run.
    """
    id: MachineID = Field(
        description="Identificador del blueprint del agente al momento del run."
    )
    version: SemanticVersion = Field(
        description="Versión semántica del blueprint al momento del run."
    )
    model: ModelSpec = Field(
        description="Spec del modelo LLM al momento del run (provider + name + params)."
    )
    governance: GovernanceConfig = Field(
        description="Config de gobernanza de budget al momento del run."
    )
    context_strategy: MachineID = Field(
        description="Clave de la estrategia de contexto al momento del run."
    )