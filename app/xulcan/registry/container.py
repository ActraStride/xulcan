"""RegistryContainer — Autocontained holder for all Xulcan provider registries.

Introduced in Issue 23. Each registry is a per-instance ProviderRegistry — never
a module-level singleton. This enables isolated test environments, multiple 
concurrent Xulcan instances, and future multi-tenant deployments.

Typing contract (intentional decoupling):
    - Infrastructure registries are typed via their ABC bases
      (for those with ABCs: BaseLedgerAdapter, BaseEventBus, BaseStateStore, BaseVaultStore).
    - Governance registries are typed via their ABC base classes directly
      (BaseBursarStrategy, BaseSentinelStrategy, BaseHumanGateStrategy, 
       BaseContextStrategy).
    - LLM adapters are typed via BaseLLMAdapter (ABC), not LLMOrchestrator
      (which is the orchestrator interface, not the adapter interface).
    
    This avoids circular dependencies while preserving full static typing and IDE support.
"""

from __future__ import annotations

from xulcan.registry.base import ProviderRegistry

# LLM base (implementation lineage)
from xulcan.llm.base import BaseLLMAdapter

# Governance ABC bases (implementation lineage)
from xulcan.governance.bursar.base import BaseBursarStrategy
from xulcan.governance.sentinel.base import BaseSentinelStrategy
from xulcan.governance.human.base import BaseHumanGateStrategy
from xulcan.context.base import BaseContextStrategy

# Infrastructure ABC bases (implementation lineage)
from xulcan.ledger.base import BaseLedgerAdapter
from xulcan.bus.base import BaseEventBus
from xulcan.memory.state.base import BaseStateStore
from xulcan.memory.vault.base import BaseVaultStore


class RegistryContainer:
    """Autocontained holder for all Xulcan provider registries.

    Each registry is a per-instance ProviderRegistry — never a module-level
    singleton. This enables isolated test environments, multiple concurrent
    Xulcan instances, and future multi-tenant deployments.

    Attributes:
        Infrastructure Registries (typed via ABC bases):
            llm: LLM model adapter registry (typed via BaseLLMAdapter)
            ledger: Event ledger repository registry (typed via BaseLedgerAdapter)
            event_bus: Event bus implementation registry (typed via BaseEventBus)
            state_store: State store (blackboard) registry (typed via BaseStateStore)
            vault: Credential vault registry (typed via BaseVaultStore)

        Governance Registries (typed via ABC bases):
            context: Context/history management strategy registry
            bursar: Budget/token governance strategy registry
            sentinel: Tool call validation/filtering strategy registry
            human_gate: Human approval gate strategy registry
    """

    def __init__(self):
        # ── Infrastructure (typed via ABC bases) ────────────────────────
        self.llm: ProviderRegistry[BaseLLMAdapter] = ProviderRegistry("LLM")
        self.ledger: ProviderRegistry[BaseLedgerAdapter] = ProviderRegistry("Ledger")
        self.event_bus: ProviderRegistry[BaseEventBus] = ProviderRegistry("EventBus")
        self.state_store: ProviderRegistry[BaseStateStore] = ProviderRegistry("StateStore")
        self.vault: ProviderRegistry[BaseVaultStore] = ProviderRegistry("Vault")

        # ── Governance (typed via ABC bases) ────────────────────────────
        # These use ABC base classes because governance strategies have shared
        # implementation patterns (config, logging, etc.) that are captured in
        # the ABC, not in kernel Protocols.
        self.context: ProviderRegistry[BaseContextStrategy] = ProviderRegistry("Context")
        self.bursar: ProviderRegistry[BaseBursarStrategy] = ProviderRegistry("Bursar")
        self.sentinel: ProviderRegistry[BaseSentinelStrategy] = ProviderRegistry("Sentinel")
        self.human_gate: ProviderRegistry[BaseHumanGateStrategy] = ProviderRegistry("HumanGate")
