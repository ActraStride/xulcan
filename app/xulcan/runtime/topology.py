# xulcan/runtime/topology.py
"""Stage-1 runtime topology objects.

Shared data layer between ManifestResolver and RuntimeAssembler.
Objects here represent infrastructure materialized from manifest resolution,
not the full runtime — that emerges in Issue 4 (ROADMAP).
"""

from __future__ import annotations

from xulcan.core.primitives import ImmutableRecord
from xulcan.manifest.schema import InfraprintManifest
from xulcan.ledger.base import BaseLedgerAdapter
from xulcan.bus.base import BaseEventBus
from xulcan.memory.state.base import BaseStateStore
from xulcan.memory.vault.base import BaseVaultStore
from xulcan.llm.base import BaseLLMAdapter


class ResolvedInfrastructure(ImmutableRecord):
    """Stage-1 runtime topology — infrastructure materialized from manifest.

    Boundary object between ManifestResolver and RuntimeAssembler.
    Contains fully instantiated adapters, not classes or registry references.
    Carries the original manifest to avoid reparsing in downstream stages.

    This is Stage-1 topology, not the final RuntimeContext.
    The assembler extends this in Issue 4 with tool routing, blueprint
    loading, and execution surfaces before handing it to ProtoKernel.
    """
    model_config = {"arbitrary_types_allowed": True}

    manifest: InfraprintManifest
    llm_instances: dict[str, BaseLLMAdapter]
    default_llm: str
    ledger: BaseLedgerAdapter
    event_bus: BaseEventBus
    state_store: BaseStateStore
    vault: BaseVaultStore