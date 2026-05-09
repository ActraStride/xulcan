# xulcan/runtime/context.py
"""RuntimeContext — fully assembled, executable runtime graph."""

from __future__ import annotations

from typing import Optional

from xulcan.core.primitives import ImmutableRecord
from xulcan.runtime.topology import ResolvedInfrastructure
from xulcan.kernel.orchestrator import ProtoKernel
from xulcan.kernel.environment import SystemEnvironment
from xulcan.llm.executor import LLMExecutor
from xulcan.tools.base import BaseToolExecutor


class RuntimeContext(ImmutableRecord):
    """Fully assembled runtime graph.

    Produced by RuntimeAssembler. Final runtime boundary before
    public API exposure in Xulcan (Issue 5).

    This is NOT global state, NOT a singleton, NOT session memory.
    One instance per Xulcan runtime.

    Fields:
        infrastructure:  Stage-1 topology from ManifestResolver.
                         Includes original manifest for introspection.
        environment:     SystemEnvironment wired with state_store, vault, event_bus.
        llm_executor:    LLMExecutor backed by RuntimeLLMRegistryAdapter.
        tool_router:     ToolRouterExecutor — assembled capability surface.
                         Routes are empty at assembly time; populated by
                         public API (@tool, add_agent, enable_sandbox) in Issue 5.
        local_executor:  LocalPythonExecutor — exposed for tool registration.
        sub_agent_executor: SubAgentExecutor — exposed for agent registration.
        sandbox_executor:   SandboxExecutor or None if Docker unavailable.
        kernel:          ProtoKernel — passive execution consumer.
    """
    model_config = {"arbitrary_types_allowed": True}

    infrastructure: ResolvedInfrastructure
    environment: SystemEnvironment
    llm_executor: LLMExecutor
    tool_router: BaseToolExecutor
    local_executor: BaseToolExecutor
    sub_agent_executor: BaseToolExecutor
    sandbox_executor: Optional[BaseToolExecutor]
    kernel: ProtoKernel
