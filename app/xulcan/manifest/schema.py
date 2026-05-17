"""xulcan/manifest/schema.py — Infraprint Manifest schema definitions.

Defines the declarative configuration structure for a Xulcan deployment.

Architectural note on AppConfig:
    AppConfig is intentionally minimal in v0.4.0. Its sole responsibility
    is to establish namespace-level governance boundaries, enabling
    hierarchical governance compilation downstream.

    Future MAS/event-bus use cases (inter-app coordination, shared budgets,
    event bus topology) may promote AppConfig into a full ontology with its
    own `app.xul.yml` specification file. No speculative fields are introduced
    in v0.4.0.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic.functional_validators import BeforeValidator

from xulcan.contracts import GovernanceConfig
from xulcan.core.primitives import (
    ImmutableRecord,
    MachineID,
    SemanticVersion,
    JsonDict,
)


# ---------------------------------------------------------------------------
# Kernel infrastructure configs
# ---------------------------------------------------------------------------


class LedgerConfig(ImmutableRecord):
    driver: MachineID = "memory"
    params: JsonDict = Field(default_factory=dict)


class StateStoreConfig(ImmutableRecord):
    driver: MachineID = "memory"
    params: JsonDict = Field(default_factory=dict)


class EventBusConfig(ImmutableRecord):
    driver: MachineID = "memory"
    params: JsonDict = Field(default_factory=dict)


class VaultConfig(ImmutableRecord):
    driver: MachineID = "env"
    params: JsonDict = Field(default_factory=dict)


class KernelConfig(ImmutableRecord):
    ledger: LedgerConfig = Field(default_factory=LedgerConfig)
    state_store: StateStoreConfig = Field(default_factory=StateStoreConfig)
    event_bus: EventBusConfig = Field(default_factory=EventBusConfig)
    vault: VaultConfig = Field(default_factory=VaultConfig)


# ---------------------------------------------------------------------------
# LLM / provider configs
# ---------------------------------------------------------------------------


class LLMInstanceConfig(ImmutableRecord):
    driver: MachineID
    model: str
    params: JsonDict = Field(default_factory=dict)


class LLMConfig(ImmutableRecord):
    default: MachineID
    instances: dict[MachineID, LLMInstanceConfig]


class ProvidersConfig(ImmutableRecord):
    llm: LLMConfig


class BlueprintsConfig(ImmutableRecord):
    paths: list[str] = Field(default_factory=list)
    autoload: bool = False


# ---------------------------------------------------------------------------
# App ontology
# ---------------------------------------------------------------------------


class AppConfig(ImmutableRecord):
    """Declarative container for a single App namespace.

    In v0.4.0, AppConfig is intentionally minimal: its sole field beyond
    ``path`` is optional ``governance``, establishing namespace-level
    governance boundaries.

    The ``path`` field maps directly to the on-disk folder that contains the
    app's agents and tools, and doubles as the root namespace passed to the
    ``tool_router``.

    Future considerations (deferred to v0.5.0+):
        - ``app.xul.yml`` specification files per app.
        - App-level event bus topology.
        - Inter-app coordination / IPC pipelines.
        - App-level Sentinel / HumanGate governance.
    """

    path: str
    governance: GovernanceConfig | None = None


def _normalize_apps_list(v: Any) -> Any:
    """Normalise legacy string app entries into AppConfig-compatible dicts.

    Supports all three YAML forms simultaneously:

    Legacy shorthand::

        apps:
          - sales
          - support

    Structured form::

        apps:
          - path: sales
            governance:
              budget: {strategy: enforced, params: {}}

    Mixed form::

        apps:
          - sales
          - path: quotations
            governance: null

    All entries are coerced into dicts before Pydantic validates them as
    ``AppConfig``. Existing dicts / already-parsed ``AppConfig`` instances are
    passed through unchanged.
    """
    if not isinstance(v, list):
        return v

    normalised: list[Any] = []
    for item in v:
        if isinstance(item, str):
            normalised.append({"path": item, "governance": None})
        else:
            # dict or already-instantiated AppConfig — pass through
            normalised.append(item)
    return normalised


# ---------------------------------------------------------------------------
# Top-level manifest
# ---------------------------------------------------------------------------


class InfraprintManifest(ImmutableRecord):
    """Top-level Infraprint manifest (xulcan.yml / Xulcanfile).

    ``apps`` accepts legacy string shorthand, structured ``AppConfig``
    dictionaries, and mixed lists — all normalised internally into
    ``list[AppConfig]`` before any further processing.
    """

    version: SemanticVersion
    kernel: KernelConfig = Field(default_factory=KernelConfig)
    providers: ProvidersConfig
    blueprints: BlueprintsConfig = Field(default_factory=BlueprintsConfig)
    apps: Annotated[
        list[AppConfig],
        BeforeValidator(_normalize_apps_list),
    ] = Field(default_factory=list)
