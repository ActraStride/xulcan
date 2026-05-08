from xulcan.core.primitives import (
    ImmutableRecord,
    MachineID,
    SemanticVersion,
    JsonDict,
)
from pydantic import Field


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


class InfraprintManifest(ImmutableRecord):
    version: SemanticVersion
    kernel: KernelConfig = Field(default_factory=KernelConfig)
    providers: ProvidersConfig
    blueprints: BlueprintsConfig = Field(default_factory=BlueprintsConfig)