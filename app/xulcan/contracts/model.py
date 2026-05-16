"""ModelSpec — especificación completa de un modelo LLM.

Contrato transversal. No pertenece a blueprint/ (inversión de dependencias)
ni a core/ (violación DDD: no es física). Vive en contracts/ como tipo
compartido entre blueprint/, history/, governance/, y la futura capa app/.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from xulcan.core.primitives import (
    ImmutableRecord,
    MachineID,
    ExternalID,
    FinitePositiveFloat,
    JsonDict,
)


class ModelSpec(ImmutableRecord):
    """Especificación tipada y completa de un modelo LLM.

    Soporta sintaxis slash para declaraciones YAML compactas:
        model: google/gemini-2.5-flash
    en lugar de:
        model:
          provider: google
          name: gemini-2.5-flash

    Attributes:
        provider: Clave del proveedor LLM (mapea a ProviderRegistry en app.py).
        name: Nombre del modelo como lo espera el proveedor en su API.
        temperature: Temperatura de muestreo. 0.0 = máximamente determinista.
        max_tokens: Tokens máximos en la respuesta. None = default del proveedor.
        params: Parámetros específicos del proveedor enviados al ConfigSchema del adaptador.
    """
    provider: MachineID = Field(
        description="Clave del proveedor LLM (mapea a ProviderRegistry en app.py)."
    )
    name: ExternalID = Field(
        description=(
            "Nombre del modelo como lo espera el proveedor en su API "
            "(e.g. 'gemini-2.5-flash', 'claude-sonnet-4-20250514')."
        )
    )
    temperature: FinitePositiveFloat = Field(
        default=0.0,
        description="Temperatura de muestreo. 0.0 = máximamente determinista."
    )
    max_tokens: int | None = Field(
        default=None,
        gt=0,
        description="Tokens máximos en la respuesta. None = default del proveedor."
    )
    params: JsonDict = Field(
        default_factory=dict,
        description=(
            "Parámetros específicos del proveedor no cubiertos por los campos estándar "
            "(e.g. top_p, seed, stop_sequences). "
            "Enviados al ConfigSchema del adaptador tal cual."
        )
    )

    @model_validator(mode='before')
    @classmethod
    def parse_slash_syntax(cls, value: Any) -> Any:
        """Expande 'provider/model-name' en un dict ModelSpec.

        Raises:
            ValueError: Si el string no contiene exactamente un '/' o
                alguno de los lados del split está vacío.
        """
        if isinstance(value, str):
            parts = value.split("/", 1)
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                raise ValueError(
                    f"ModelSpec string inválido '{value}'. "
                    "Formato esperado: 'provider/model-name' "
                    "(e.g. 'google/gemini-2.5-flash', 'anthropic/claude-sonnet-4-20250514')."
                )
            return {"provider": parts[0].strip(), "name": parts[1].strip()}
        return value