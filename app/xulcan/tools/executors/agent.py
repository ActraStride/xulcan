"""Hierarchical Swarm Execution Adapter.

Allows Xulcan Agents to invoke other Xulcan Agents as tools.
Implements 'Memory Teleportation' (Fractal Swarm) to seamlessly pass large
data objects from a child agent's memory to the parent agent's memory.
"""

from __future__ import annotations

import json
import logging
import asyncio
from typing import TYPE_CHECKING

from xulcan.tools.base import BaseToolExecutor
from xulcan.protocol.tools import ToolCall, ToolDefinition
from xulcan.protocol.message import ToolMessage
from xulcan.blueprint.schema import AgentBlueprint
from xulcan.kernel.environment import SystemEnvironment

# Avoid circular imports at runtime
if TYPE_CHECKING:
    from xulcan.kernel.orchestrator import ProtoKernel

logger = logging.getLogger("xulcan.tools.executors.subagent")


class SubAgentExecutor(BaseToolExecutor):
    """Adapter that executes other Xulcan Agents as tools (Hierarchical Swarm).
    
    Uses Setter Injection (Late Binding) for the ProtoKernel to prevent
    circular dependency issues during system initialization.
    """

    def __init__(self, environment: SystemEnvironment | None = None) -> None:
        self.environment = environment
        self.kernel: ProtoKernel | None = None
        self._blueprints: dict[str, AgentBlueprint] = {}
        self._definitions: dict[str, ToolDefinition] = {}

    def bind_kernel(self, kernel: ProtoKernel) -> None:
        """Injects the cognitive engine after instantiation."""
        self.kernel = kernel
        logger.debug("🔗 SubAgentExecutor successfully bound to ProtoKernel.")

    def register_agent(self, definition: ToolDefinition, blueprint: AgentBlueprint) -> None:
        """Registers an entire Agent Blueprint as an available tool."""
        name = definition.function.name
        self._blueprints[name] = blueprint
        self._definitions[name] = definition
        logger.info(f"🤖 Sub-Agent registered as tool: '{name}'")

    def get_definition(self, name: str) -> ToolDefinition | None:
        return self._definitions.get(name)

    # ── MÉTODOS FALTANTES DEL CONTRATO (PROTOCOL) ───────────────────────────
    def get_definitions(self, tool_names: list[str]) -> list[ToolDefinition]:
        """Fulfills the ToolExecutor Protocol requirement."""
        return [self._definitions[name] for name in tool_names if name in self._definitions]
    # ────────────────────────────────────────────────────────────────────────

    async def execute(self, call: ToolCall) -> ToolMessage:
        logger.debug(f"▶️  SUB-AGENT EXEC: Waking up agent '{call.name}'")
        
        if not self.kernel:
            raise RuntimeError(
                "💥 Invalid Architecture: SubAgentExecutor has no bound Kernel. "
                "You must call bind_kernel() before execution."
            )
            
        if call.name not in self._blueprints:
            error_payload = json.dumps({"error": f"Agent tool '{call.name}' not found."})
            return ToolMessage(
                tool_call_id=call.id,
                name=call.name,
                content=error_payload
            )

        # Usamos el acceso directo de Pydantic
        context = call.context or {}
        parent_run_id = context.get("run_id")
        
        if not parent_run_id:
            logger.warning(
                f"⚠️ Traceability warning: No parent run_id found in context "
                f"for sub-agent '{call.name}'."
            )
            parent_run_id = f"unknown_parent_{call.id}"
            
        try:
            blueprint = self._blueprints[call.name]
            prompt = call.arguments.get("prompt") or call.arguments.get("task", "")
            
            # ── 1. SPAWN CHILD KERNEL RUN ───────────────────────────────────────
            child_run_id, response = await self.kernel.execute_run(
                blueprint=blueprint, 
                user_input=prompt,
                parent_id=parent_run_id
            )
            
            # ── 2. MEMORY TELEPORTATION (Fractal Swarm) ─────────────────────────
            output_memory_key = call.arguments.get("output_memory_key")
            
            if output_memory_key and self.environment and self.environment.state_store:
                logger.debug(
                    f"🧠 Synchronizing key '{output_memory_key}' "
                    f"from Child ({child_run_id}) to Parent ({parent_run_id})..."
                )
                
                # ADVERTENCIA: Como indicaste en tu propio comentario, el Kernel
                # borra la memoria del hijo al terminar (estado COMPLETED).
                # Si esto falla, haz que el hijo escriba directamente en parent_run_id
                child_data = await self.environment.state_store.get(child_run_id, output_memory_key)
                
                if child_data is not None:
                    await self.environment.state_store.set(parent_run_id, output_memory_key, child_data)
                    content = f"✅ Task completed. Data securely saved to shared memory under key: '{output_memory_key}'."
                else:
                    content = f"⚠️ Task completed, but no data was found under '{output_memory_key}' in the child's memory."
            else:
                content = str(response.content) if response and response.content else "No output generated."
                
            logger.info(f"✅ SUB-AGENT RESULT: '{call.name}' (Child ID: {child_run_id}) completed successfully.")
            
        except Exception as e:
            logger.error(f"❌ SUB-AGENT ERROR ({call.name}): {str(e)}", exc_info=True)
            content = json.dumps({
                "error": "Sub-agent execution failed",
                "details": str(e)
            })

        return ToolMessage(
            tool_call_id=call.id, 
            name=call.name, 
            content=content
        )

    # ── MÉTODOS FALTANTES DEL CONTRATO (PROTOCOL) ───────────────────────────
    async def execute_batch(self, calls: list[ToolCall]) -> list[ToolMessage]:
        """Execute multiple sub-agents concurrently safely."""
        async def safe_execute(call: ToolCall) -> ToolMessage:
            try:
                return await self.execute(call)
            except Exception as e:
                logger.error(f"Sub-agent {call.name} batch execution failed: {e}", exc_info=True)
                return ToolMessage(
                    tool_call_id=call.id,
                    name=call.name,
                    content=json.dumps({"error": f"Batch execution failed: {str(e)}"})
                )

        results = await asyncio.gather(*(safe_execute(call) for call in calls))
        return list(results)