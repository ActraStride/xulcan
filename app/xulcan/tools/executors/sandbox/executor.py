"""Sandbox Executor for isolated tool execution.

Adapter that connects the Xulcan Kernel to an isolated execution environment
(Docker, Firecracker, WASM). Implements stateless Lazy Initialization to 
conserve compute resources until the agent actually needs to interact with
the OS or filesystem.
"""

from __future__ import annotations

import os
import json
import logging
import asyncio

from xulcan.tools.base import BaseToolExecutor
from xulcan.protocol.tools import ToolCall, ToolDefinition
from xulcan.protocol.message import ToolMessage
from xulcan.tools.executors.sandbox.provider import IsolationProvider
from xulcan.kernel.environment import SystemEnvironment

logger = logging.getLogger("xulcan.tools.executors.sandbox")


class SandboxExecutor(BaseToolExecutor):
    """Executes tools within a secure, isolated sandbox environment.
    
    Features:
        - Lazy Initialization: Only starts the sandbox on the first tool call.
        - Persistent Workspaces: Maps environment workspace_ids to isolated volumes.
        - File I/O & Execution: Safely runs Python and Bash commands.
    """

    def __init__(
        self, 
        provider: IsolationProvider, 
        environment: SystemEnvironment | None = None
    ) -> None:
        self.provider = provider
        self.environment = environment
        self._definitions: dict[str, ToolDefinition] = {}

    def register_tool(self, definition: ToolDefinition) -> None:
        """Registers a tool definition supported by this sandbox."""
        name = definition.function.name
        self._definitions[name] = definition
        logger.debug(f"🛡️ Sandbox tool registered: '{name}'")

    def get_definition(self, name: str) -> ToolDefinition | None:
        """Retrieves the JSON schema for a registered tool."""
        return self._definitions.get(name)

    # ── TOOL EXECUTOR PROTOCOL FULFILLMENT ───────────────────────────────────

    def get_definitions(self, tool_names: list[str]) -> list[ToolDefinition]:
        """Retrieves the JSON schemas for the requested tools."""
        return [self._definitions[name] for name in tool_names if name in self._definitions]

    async def execute_batch(self, calls: list[ToolCall]) -> list[ToolMessage]:
        """Executes multiple sandbox tools concurrently."""
        async def safe_execute(call: ToolCall) -> ToolMessage:
            try:
                return await self.execute(call)
            except Exception as e:
                logger.error(f"Sandbox batch execution failed for '{call.name}': {e}", exc_info=True)
                return self._build_error_message(call, str(e))

        results = await asyncio.gather(*(safe_execute(call) for call in calls))
        return list(results)

    # ─────────────────────────────────────────────────────────────────────────

    async def execute(self, call: ToolCall) -> ToolMessage:
        """Dispatches the tool call to the isolated environment."""
        logger.debug(f"▶️  SANDBOX EXEC: '{call.name}'")

        if call.name not in self._definitions:
            return self._build_error_message(
                call, 
                f"Tool '{call.name}' is not registered in this SandboxExecutor."
            )

        # ── 1. Traceability and Session Resolution ───────────────────────────
        context = call.context or {}
        run_id = context.get("run_id")
        
        if not run_id:
            logger.warning(
                f"⚠️ ToolCall {call.id} lacks 'run_id' in context. "
                f"Memory resolution might fail."
            )
            run_id = f"fallback_{call.id}"
            
        # Priority 1: Persistent Workspace ID from the SystemEnvironment
        if self.environment and self.environment.workspace_id:
            session_id = self.environment.workspace_id
        # Priority 2: Ephemeral container for this specific run
        else:
            session_id = str(run_id)
            
        try:
            # ── 2. Lazy Initialization (Stateless) ───────────────────────────
            if not await self.provider.is_active(session_id):
                logger.info(f"⚡ Lazy initializing sandbox machine for session: {session_id}")
                
                # The Physical Bridge: Map the host staging directory
                # Corresponds to PDF §5.3 (Nota sobre persistencia)
                host_workspace_path = os.path.abspath("./xulcan_staging")
                
                await self.provider.start_session(
                    session_id=session_id, 
                    workspace_path=host_workspace_path
                )
                
            # ── 3. Routing & Robust Execution ────────────────────────────────
            result_data = None
            
            if call.name == "sandbox_run_python":
                # Forced cast to string to satisfy Pylance
                code = str(call.arguments.get("code", ""))
                temp_script = "/workspace/.xulcan_temp.py"
                await self.provider.write_file(session_id, temp_script, code)
                result_data = await self.provider.execute_command(
                    session_id, 
                    f"python3 {temp_script}"
                )

            elif call.name == "sandbox_run_bash":
                command = str(call.arguments.get("command", ""))
                result_data = await self.provider.execute_command(session_id, command)
                
                # FIX: If the bash command produces no output, explicitly tell
                # the LLM it succeeded so it doesn't think it failed silently.
                stdout = str(result_data.get("stdout", "")).strip()
                stderr = str(result_data.get("stderr", "")).strip()
                
                if stdout or stderr:
                    output_str = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                else:
                    output_str = "Command executed successfully (No terminal output)."
                
                # Format response for better LLM comprehension
                result_data = {"status": "success", "output": output_str}
                
            elif call.name == "sandbox_read_file":
                filepath = str(call.arguments.get("file_path", ""))
                content = await self.provider.read_file(session_id, filepath)
                result_data = {"status": "success", "content": content}

            elif call.name == "sandbox_write_file":
                filepath = str(call.arguments.get("file_path", ""))
                
                # The ToolRouterExecutor already resolved Jinja2 variables
                content = str(call.arguments.get("content", ""))
                
                # Legacy support: If the LLM explicitly used the old 'memory_key' argument
                if not content and "memory_key" in call.arguments and self.environment and self.environment.state_store:
                    memory_key = str(call.arguments["memory_key"])
                    # CRITICAL: Use run_id, NOT session_id, to access volatile memory
                    content_raw = await self.environment.state_store.get(run_id, memory_key)
                    content = json.dumps(content_raw) if isinstance(content_raw, (dict, list)) else str(content_raw)

                await self.provider.write_file(session_id, filepath, content)
                result_data = {
                    "status": "success", 
                    "message": f"File '{filepath}' saved successfully."
                }
                
            else:
                raise ValueError(f"Unknown sandbox action requested: '{call.name}'")

            # ── 4. Response Formatting ───────────────────────────────────────
            logger.debug(f"✅ SANDBOX RESULT ({call.name}): Completed successfully.")
            return ToolMessage(
                tool_call_id=call.id,
                name=call.name,
                content=json.dumps(result_data)
            )

        except Exception as e:
            logger.error(f"❌ SANDBOX ERROR ({call.name}): {str(e)}", exc_info=True)
            return self._build_error_message(call, str(e))

    def _build_error_message(self, call: ToolCall, error_str: str) -> ToolMessage:
        """Formats errors safely for the LLM to understand and retry."""
        error_payload = json.dumps({
            "error": f"The isolated environment failed: {error_str}",
            "hint": "Check syntax, file paths, or permissions."
        })
        return ToolMessage(
            tool_call_id=call.id,
            name=call.name,
            content=error_payload
        )

    async def cleanup_session(self, session_id: str) -> None:
        """Terminates the sandbox environment."""
        logger.info(f"🧹 Cleaning up sandbox machine for session: {session_id}")
        await self.provider.terminate_session(session_id)