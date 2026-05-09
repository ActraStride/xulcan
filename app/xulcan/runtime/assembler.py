# xulcan/runtime/assembler.py
"""RuntimeAssembler — Stage-2 of Xulcan's runtime materialization pipeline."""

from __future__ import annotations

import logging

from typing import Optional

from xulcan.runtime.topology import ResolvedInfrastructure
from xulcan.runtime.context import RuntimeContext
from xulcan.runtime.llm_registry_adapter import RuntimeLLMRegistryAdapter
from xulcan.registry.container import RegistryContainer

from xulcan.kernel.environment import SystemEnvironment
from xulcan.kernel.runtime import ProtoKernel
from xulcan.llm.executor import LLMExecutor

from xulcan.tools.executors.local import LocalPythonExecutor
from xulcan.tools.executors.agent import SubAgentExecutor
from xulcan.tools.router import ToolRouterExecutor
from xulcan.tools.executors.sandbox.docker import DockerProvider
from xulcan.tools.executors.sandbox.executor import SandboxExecutor

logger = logging.getLogger("xulcan.runtime.assembler")


class RuntimeAssembler:
    """Wires the execution graph and constructs the executable runtime.

    Receives Stage-1 topology (ResolvedInfrastructure) and governance
    registries (RegistryContainer), produces RuntimeContext.

    Wiring order:
        1. SystemEnvironment  (requires state_store, vault, event_bus)
        2. LLM surface        (RuntimeLLMRegistryAdapter → LLMExecutor)
        3. Tool executors     (each receives environment)
        4. ToolRouterExecutor (receives environment; routes populated later)
        5. SandboxExecutor    (optional — graceful on Docker absence)
        6. ProtoKernel        (receives all surfaces + governance registries)
        7. Post-construction  (SubAgentExecutor.bind_kernel)

    Note on tool routing:
        ToolRouterExecutor._routing_table is empty after assembly.
        Routes are registered by the public API (@tool, add_agent,
        enable_sandbox) in Issue 5. The assembler builds capabilities,
        not routes.
    """

    def __init__(
        self,
        infrastructure: ResolvedInfrastructure,
        registries: RegistryContainer,
    ):
        self._infrastructure = infrastructure
        self._registries = registries

    async def assemble(self) -> RuntimeContext:
        infra = self._infrastructure

        # ── 1. SystemEnvironment ─────────────────────────────────────────
        # Central shared context for all execution surfaces.
        # Required by: context strategies, tool executors, kernel.
        environment = SystemEnvironment(
            state_store=infra.state_store,
            vault_store=infra.vault,
            event_bus=infra.event_bus,
            workspace_id=None,
        )
        logger.debug("✓ SystemEnvironment assembled")

        # ── 2. LLM Execution Surface ─────────────────────────────────────
        # RuntimeLLMRegistryAdapter bridges pre-instantiated adapters
        # to legacy registry.build() contract. LLMExecutor unchanged.
        llm_registry_adapter = RuntimeLLMRegistryAdapter(infra.llm_instances)
        llm_executor = LLMExecutor(registry=llm_registry_adapter)
        logger.debug("✓ LLMExecutor assembled via RuntimeLLMRegistryAdapter")

        # ── 3. Tool Executors ────────────────────────────────────────────
        # Each executor receives environment for state/vault access.
        # SubAgentExecutor receives kernel via post-construction binding.
        local_executor = LocalPythonExecutor(environment=environment)
        sub_agent_executor = SubAgentExecutor(environment=environment)
        logger.debug("✓ LocalPythonExecutor and SubAgentExecutor assembled")

        # ── 4. Tool Router ───────────────────────────────────────────────
        # Routing table is empty here — populated by public API in Issue 5.
        # The router is the execution surface the kernel calls.
        tool_router = ToolRouterExecutor(environment=environment)
        logger.debug("✓ ToolRouterExecutor assembled (routing table empty — populated by public API)")

        # ── 5. Sandbox (optional) ────────────────────────────────────────
        sandbox_executor: Optional[SandboxExecutor] = None
        try:
            sandbox_executor = SandboxExecutor(
                provider=DockerProvider(),
                environment=environment,
            )
            logger.debug("✓ SandboxExecutor assembled (Docker available)")
        except Exception as e:
            logger.warning(f"⚠ Docker unavailable — sandbox tools disabled: {e}")

        # ── 6. ProtoKernel ───────────────────────────────────────────────
        # Passive execution consumer. Receives all wired surfaces.
        # Governance registries come from RegistryContainer.
        kernel = ProtoKernel(
            repository=infra.ledger,
            llm_executor=llm_executor,
            tool_executor=tool_router,
            context_registry=self._registries.context,
            bursar_registry=self._registries.bursar,
            sentinel_registry=self._registries.sentinel,
            human_gate_registry=self._registries.human_gate,
            environment=environment,
        )
        logger.debug("✓ ProtoKernel assembled")

        # ── 7. Post-Construction Cyclic Binding ──────────────────────────
        # SubAgentExecutor needs kernel to spawn child runs.
        # ProtoKernel needs tool_router which includes SubAgentExecutor.
        # Both must be fully constructed before this binding.
        sub_agent_executor.bind_kernel(kernel)
        logger.debug("✓ SubAgentExecutor ← kernel binding complete")

        return RuntimeContext(
            infrastructure=infra,
            environment=environment,
            llm_executor=llm_executor,
            tool_router=tool_router,
            local_executor=local_executor,
            sub_agent_executor=sub_agent_executor,
            sandbox_executor=sandbox_executor,
            kernel=kernel,
        )
