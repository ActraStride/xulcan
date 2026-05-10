"""Tool Router and Execution Dispatcher.

Acts as the Main Registry AND the Main Executor for the Kernel.
Routes incoming ToolCalls to the appropriate specific Executor (Adapter),
such as a LocalPythonExecutor, SandboxExecutor, or SubAgentExecutor.
"""

from __future__ import annotations

import logging
import json

from xulcan.tools.base import BaseToolExecutor
from xulcan.protocol.tools import ToolCall, ToolDefinition
from xulcan.protocol.message import ToolMessage

from xulcan.kernel.environment import SystemEnvironment
from xulcan.utils.template import render_template

logger = logging.getLogger("xulcan.tools.registry")


class ToolRouterExecutor(BaseToolExecutor):
    """Dispatches tool execution requests to their registered handlers.
    
    This class acts as a Composite/Facade for tool execution. The Kernel
    calls this router, which then resolves dynamic arguments (via Jinja2)
    and passes the call to the actual implementation.
    """
    
    def __init__(self, environment: SystemEnvironment | None = None) -> None:
        self.environment = environment
        self._routing_table: dict[str, BaseToolExecutor] = {}  # "chat.save" → executor
        self._llm_name_index: dict[str, str] = {}              # "chat__save" → "chat.save"

    def get_definitions(self, tool_names: list[str]) -> list[ToolDefinition]:
        """Returns the JSON schemas for the requested tools.
        
        Aggregates definitions from all registered executors to build the
        final tool injection payload for the LLM.
        """
        definitions =[]
        for name in tool_names:
            # Resolve LLM name to route key
            route_key = self._llm_name_index.get(name, name)
            if route_key in self._routing_table:
                executor = self._routing_table[route_key]
                
                # Check if the executor can return a definition dynamically
                # (Used by executors that handle multiple tools, like Sandbox)
                if hasattr(executor, 'get_definition'):
                    schema = executor.get_definition(name)
                    if schema:
                        definitions.append(schema)
                    else:
                        logger.warning(
                            f"⚠️ Tool '{name}' routed, but executor returned empty schema."
                        )
                
                # Fallback for legacy 1-to-1 executors that store it as a property
                elif hasattr(executor, 'definition'):
                    definitions.append(executor.definition)
                else:
                    logger.warning(
                        f"⚠️ Tool '{name}' has no definition logic in its executor."
                    )
            else:
                raise ValueError(
                    f"Tool '{name}' requested by Blueprint but not routed in the Registry."
                )
                
        return definitions

    def route_tool(self, route_key: str, llm_name: str, executor: BaseToolExecutor) -> None:
        """Bind a specific tool name to a specific execution adapter."""
        self._routing_table[route_key] = executor
        self._llm_name_index[llm_name] = route_key
        logger.debug(f"🔀 Route mapped: '{route_key}' (LLM: '{llm_name}') -> {executor.__class__.__name__}")

    async def execute(self, call: ToolCall) -> ToolMessage:
        """Executes the tool call by routing it to the registered executor.
        
        Intercepts the arguments before execution to resolve Jinja2 templates
        against the agent's StateStore memory.
        """
        # Resolve LLM name (e.g., chat__save) to Route Key (e.g., chat.save)
        route_key = self._llm_name_index.get(call.name, call.name)
        executor = self._routing_table.get(route_key)
        
        if not executor:
            error_payload = json.dumps({"error": f"Tool '{call.name}' not found in registry."})
            return ToolMessage(
                tool_call_id=call.id, 
                name=call.name, 
                content=error_payload
            )
        
        try:
            # =================================================================
            # JINJA2 DYNAMIC RESOLUTION: StateStore Memory -> Tool Arguments
            # =================================================================
            if self.environment and self.environment.state_store:
                context_meta = getattr(call, "context", {}) or {}
                run_id = context_meta.get("run_id")
                
                if run_id:
                    # Fast-path: Only fetch memory if templates are actually used
                    args_str = str(call.arguments)
                    if "{{" in args_str:
                        # Use the highly optimized parallel memory resolver
                        memory_dict = await self.environment.resolve_memory(run_id)
                        
                        new_args = {}
                        for k, v in call.arguments.items():
                            if isinstance(v, str) and "{{" in v:
                                try:
                                    new_args[k] = render_template(v, memory_dict)
                                except Exception as template_err:
                                    logger.error(
                                        f"⚠️ Jinja template error in Router for '{call.name}': "
                                        f"{template_err}. Passing raw string as fallback."
                                    )
                                    new_args[k] = v  # Safe fallback
                            else:
                                new_args[k] = v
                                
                        # Immutability: Create a copy of the ToolCall with resolved args
                        call = call.model_copy(update={"arguments": new_args})
                        logger.debug(f"🪄 ToolRouter: Arguments resolved from memory for '{call.name}'.")

            # Delegate to the final executor (Sandbox, Local Python, SubAgent, etc.)
            return await executor.execute(call)
            
        except Exception as e:
            logger.error(f"💥 Router execution failed for '{call.name}': {str(e)}", exc_info=True)
            error_payload = json.dumps({
                "error": "Router execution failed",
                "details": str(e)
            })
            return ToolMessage(
                tool_call_id=call.id, 
                name=call.name, 
                content=error_payload
            )