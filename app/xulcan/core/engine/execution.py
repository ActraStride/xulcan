"""Execution engine for tool orchestration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from xulcan.tools.runner import ToolRunner
from xulcan.core.llm.adapters.base import BaseAdapter


class ExecutionError(Exception):
    """Exception raised when tool execution fails."""


class ExecutionEngine:
    """Engine for executing tools with retry logic and error handling."""

    def __init__(self, runner: ToolRunner, adapter: BaseAdapter) -> None:
        self.runner = runner
        self.adapter = adapter

    async def execute_tool(self, tool_call: Dict[str, Any], max_retries: int = 3) -> Any:
        converted = self.adapter.convert_tool_call(tool_call)
        tool_name = converted["tool_name"]
        inputs = converted["inputs"]

        last_exception: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                return await self.runner.run_tool_async(tool_name, inputs)
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                else:
                    break

        if last_exception:
            raise ExecutionError(
                f"Tool '{tool_name}' execution failed after retries: {last_exception}"
            )
        raise ExecutionError("Tool execution failed for unknown reason")

    async def execute_tools_parallel(
        self, tool_calls: List[Dict[str, Any]], max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        tool_names: List[str] = []
        for tool_call in tool_calls:
            try:
                tool_names.append(self.adapter.convert_tool_call(tool_call).get("tool_name", "unknown"))
            except Exception:
                tool_names.append("unknown")

        tasks = [
            asyncio.create_task(self.execute_tool(tool_call, max_retries=max_retries))
            for tool_call in tool_calls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: List[Dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(
                    {
                        "tool": tool_names[i],
                        "success": False,
                        "error": str(result),
                    }
                )
            else:
                processed.append(
                    {
                        "tool": tool_names[i],
                        "success": True,
                        "result": result,
                    }
                )
        return processed

    async def execute_tools_sequential(
        self, tool_calls: List[Dict[str, Any]], max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for tool_call in tool_calls:
            try:
                tool_name = self.adapter.convert_tool_call(tool_call).get("tool_name", "unknown")
            except Exception:
                tool_name = "unknown"
            try:
                result = await self.execute_tool(tool_call, max_retries=max_retries)
                results.append(
                    {
                        "tool": tool_name,
                        "success": True,
                        "result": result,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "tool": tool_name,
                        "success": False,
                        "error": str(e),
                    }
                )
        return results
