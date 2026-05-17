import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any, Union

from xulcan.blueprint.schema import AgentBlueprint
from xulcan.protocol.tools import ToolDefinition
from xulcan.system.naming import random_agent_name

logger = logging.getLogger("xulcan.runtime.loaders.blueprint_loader")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA VERSION CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

CURRENT_SCHEMA_VERSION = "2.0"
"""Current blueprint schema version. Bump this when making breaking changes."""

SUPPORTED_VERSIONS = {"2.0"}
"""Schema versions accepted by this version of Xulcan."""


class SchemaVersionError(ValueError):
    """Raised when a blueprint uses an unsupported schema version."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# BLUEPRINT LOADER
# ═══════════════════════════════════════════════════════════════════════════════

class BlueprintLoader:

    # =========================================================
    # 1. SCHEMA VERSION VALIDATION
    # =========================================================
    @staticmethod
    def _validate_schema_version(data: Dict[str, Any]) -> None:
        """Validates the blueprint schema version before Pydantic validation.

        Raises:
            SchemaVersionError: If schema version is missing or unsupported.
        """
        schema_version = data.get("xulcan_version")

        if schema_version is None:
            raise SchemaVersionError(
                f"Blueprint '{data.get('id', 'unknown')}' is missing the required "
                f"'xulcan_version: \"2.0\"' declaration. "
                f"Supported versions: {sorted(SUPPORTED_VERSIONS)}."
            )

        if schema_version not in SUPPORTED_VERSIONS:
            raise SchemaVersionError(
                f"Blueprint '{data.get('id', 'unknown')}' uses schema version "
                f"'{schema_version}', which is not supported by this version of Xulcan.\n"
                f"Supported versions: {sorted(SUPPORTED_VERSIONS)}."
            )

    # =========================================================
    # 2. EL NÚCLEO LÓGICO (Solo maneja diccionarios de Python)
    # =========================================================
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> AgentBlueprint:
        """Hidrata un Blueprint desde un diccionario crudo, aplicando lógica de negocio."""

        # ════════════════════════════════════════════════════════
        # A. VALIDAR SCHEMA VERSION PRIMERO
        # ════════════════════════════════════════════════════════
        BlueprintLoader._validate_schema_version(data)

        # ════════════════════════════════════════════════════════
        # B. AUTOGENERAR NOMBRE SI FALTA
        # ════════════════════════════════════════════════════════
        if not data.get("name"):
            epic_name = random_agent_name()
            data["name"] = epic_name
            if not data.get("id"):
                data["id"] = f"agent-{epic_name.lower().replace(' ', '-')}"

            logger.info(f"Nuevo Agente Forjado: {epic_name} ({data['id']})")

        # ════════════════════════════════════════════════════════
        # C. VALIDAR CON PYDANTIC (el sugar parser se ejecuta aquí)
        # ════════════════════════════════════════════════════════
        return AgentBlueprint.model_validate(data)

    # =========================================================
    # 3. LOS ADAPTADORES DE FORMATO (YAML Strings)
    # =========================================================
    @classmethod
    def from_yaml_string(cls, yaml_content: str) -> AgentBlueprint:
        """Carga un Blueprint directamente desde un texto en formato YAML (Ej: desde una API HTTP)."""
        data = yaml.safe_load(yaml_content)
        if not data:
            raise ValueError("El YAML proporcionado está vacío o es inválido.")
        return cls.from_dict(data)

    # =========================================================
    # 4. LOS ADAPTADORES DE I/O (Disco Duro)
    # =========================================================
    @classmethod
    def from_file(cls, file_path: Union[str, Path]) -> AgentBlueprint:
        """Carga un Blueprint leyendo un archivo del disco."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"No se encontró el Blueprint en: {path}")

        with open(path, "r", encoding="utf-8") as f:
            yaml_content = f.read()

        # Reutilizamos la lógica del string
        return cls.from_yaml_string(yaml_content)

    # (Puedes aplicar este mismo patrón exacto a load_tools)
