"""Local Python Tool Executor.

Adapter that executes registered Python functions in the same process.
Supports smart dependency injection for OS-level features, allowing tools
to transparently access the StateStore, Environment, and current Run ID
without exposing these parameters to the LLM.
"""

from __future__ import annotations

import json
import asyncio
import logging
import inspect
from collections.abc import Callable
from typing import Any

from xulcan.tools.base import BaseToolExecutor
from xulcan.protocol.tools import ToolCall, ToolDefinition
from xulcan.protocol.message import ToolMessage
from xulcan.kernel.environment import SystemEnvironment

logger = logging.getLogger("xulcan.tools.executors.local")


class LocalPythonExecutor(BaseToolExecutor):
    """Adapter that executes registered Python functions natively.
    
    Features:
        - Synchronous and asynchronous function support.
        - Non-blocking execution of sync functions via thread pools.
        - Dependency injection for 'run_id', 'environment', and 'state_store'.
        - Safe error boundaries capturing tracebacks into ToolMessages.
    """

    def __init__(self, environment: SystemEnvironment | None = None) -> None:
        self.environment = environment
        self._functions: dict[str, Callable[..., Any]] = {}
        self._definitions: dict[str, ToolDefinition] = {} 

    def register_function(self, definition: ToolDefinition, func: Callable[..., Any]) -> None:
        """Registers a Python function with its corresponding ToolDefinition."""
        name = definition.function.name
        self._functions[name] = func
        self._definitions[name] = definition
        logger.debug(f"🔧 Local function registered: '{name}'")

    def get_definition(self, name: str) -> ToolDefinition | None:
        """Retrieves the JSON schema definition for a registered function."""
        return self._definitions.get(name)

    def get_definitions(self, tool_names: list[str]) -> list[ToolDefinition]:
        """Retrieves the JSON schemas for a list of requested tools.
        
        Fulfills the ToolExecutor Protocol requirement for the Kernel.
        """
        return [self._definitions[name] for name in tool_names if name in self._definitions]

    async def execute(self, call: ToolCall) -> ToolMessage:
        """Executes the mapped Python function and injects OS dependencies."""
        logger.debug(f"▶️  Executing local tool: '{call.name}'")
        
        if call.name not in self._functions:
            error_payload = json.dumps({"error": f"Function '{call.name}' not found."})
            return ToolMessage(
                tool_call_id=call.id,
                name=call.name,
                content=error_payload
            )
            
        try:
            # ── 1. Execution Context Extraction ─────────────────────────────────
            # Extract out-of-band metadata injected by the Kernel
            context_meta = call.context or {}
            run_id = context_meta.get("run_id", f"fallback_{call.id}")

            func = self._functions[call.name]
            clean_args = dict(call.arguments)
            
            # ── 2. Smart Dependency Injection ───────────────────────────────────
            # Inspect the Python function signature. If it requests specific 
            # OS-level dependencies, inject them automatically. This intentionally
            # overwrites any hallucinatory parameters passed by the LLM.
            sig = inspect.signature(func)
            
            if "run_id" in sig.parameters:
                clean_args["run_id"] = run_id
                
            if "environment" in sig.parameters and self.environment:
                clean_args["environment"] = self.environment
                
            # Legacy/Direct access to state_store
            if "state_store" in sig.parameters and self.environment and self.environment.state_store:
                clean_args["state_store"] = self.environment.state_store

            # ── 3. Execution ────────────────────────────────────────────────────
            if asyncio.iscoroutinefunction(func):
                result = await func(**clean_args)
            else:
                # Offload synchronous functions to a background thread to prevent
                # blocking the main asyncio Event Loop (vital for concurrent runs).
                result = await asyncio.to_thread(func, **clean_args)
            
            logger.debug(f"✅ Local tool '{call.name}' completed successfully.")
            
            # Ensure the result is properly serialized for the LLM
            content = result if isinstance(result, str) else json.dumps(result)
            
        except Exception as e:
            logger.error(f"❌ Local execution failed for '{call.name}': {str(e)}", exc_info=True)
            content = json.dumps({
                "error": "Execution failed", 
                "details": str(e)
            })

        return ToolMessage(
            tool_call_id=call.id, 
            name=call.name, 
            content=content
        )

    async def execute_batch(self, calls: list[ToolCall]) -> list[ToolMessage]:
        """Execute multiple tool calls concurrently safely.
        
        Fulfills the ToolExecutor Protocol requirement. Prevents one failing 
        tool from crashing the entire batch of concurrent executions.
        """
        async def safe_execute(call: ToolCall) -> ToolMessage:
            try:
                return await self.execute(call)
            except Exception as e:
                logger.error(f"Tool {call.name} batch execution failed: {e}", exc_info=True)
                return ToolMessage(
                    tool_call_id=call.id,
                    name=call.name,
                    content=json.dumps({"error": f"Batch execution failed: {str(e)}"})
                )

        results = await asyncio.gather(*(safe_execute(call) for call in calls))
        return list(results)