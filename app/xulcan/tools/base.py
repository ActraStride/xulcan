"""Base adapter for Tool Executors.

Provides a foundational implementation for executing tool calls, including
a default parallel batch execution strategy that safely catches and reports
errors back to the LLM without crashing the orchestration loop.
"""

from __future__ import annotations

import logging
import asyncio
import json
from abc import ABC, abstractmethod

from xulcan.kernel.interfaces import ToolExecutor
from xulcan.protocol.tools import ToolCall
from xulcan.protocol.message import ToolMessage

logger = logging.getLogger("xulcan.executor")


class BaseToolExecutor(ToolExecutor, ABC):
    """Abstract base class for all tool execution environments.

    Implementers only need to provide the single-tool `execute` logic.
    The batch execution is handled automatically via concurrent asyncio tasks.
    """
    
    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolMessage:
        """Execute a single tool call and return the result.
        
        Args:
            call: The tool call details (name, arguments, context).
            
        Returns:
            A ToolMessage containing the execution result (usually a JSON string).
        """
        pass

    async def execute_batch(self, calls: list[ToolCall]) -> list[ToolMessage]:
        """Safely executes multiple tool calls concurrently.
        
        Uses asyncio.gather to run tools in parallel. Wraps each execution
        in a safety block: if a tool raises a Python exception, the error
        is caught, logged, and formatted as a ToolMessage so the LLM knows
        the tool failed and can attempt to recover or apologize.
        """
        
        async def safe_execute(call: ToolCall) -> ToolMessage:
            try:
                return await self.execute(call)
            except Exception as e:
                logger.error(
                    f"🔧 Tool '{call.name}' execution failed: {e}", 
                    exc_info=True
                )
                
                # Use json.dumps to safely escape any quotes or newlines in the error.
                # Invalid JSON here would break the LLM's parsing context.
                error_payload = json.dumps({
                    "error": "Execution failed",
                    "details": str(e)
                })
                
                return ToolMessage(
                    tool_call_id=call.id,
                    name=call.name,
                    content=error_payload
                )

        # Run all tool calls concurrently
        results = await asyncio.gather(*(safe_execute(call) for call in calls))
        
        return list(results)