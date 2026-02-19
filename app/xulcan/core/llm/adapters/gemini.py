"""Gemini adapter for Xulcan tools."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import BaseAdapter
from xulcan.tools.registry import ToolRegistry
from xulcan.tools.base import BaseTool


class GeminiAdapter(BaseAdapter):
    """Adapter for Google Gemini function calling format."""

    def export_tools(self, registry: ToolRegistry) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        for tool_class in registry.list_tools().values():
            tools.append(self.export_tool(tool_class))
        return tools

    def export_tool(self, tool_class: type[BaseTool]) -> Dict[str, Any]:
        schema = tool_class.model_json_schema()
        return {
            "name": tool_class.get_name(),
            "description": tool_class.get_description(),
            "parameters": schema,
        }

    def convert_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        # Gemini function calls are often {"function_call": {"name":..., "args": {...}}}
        function_call = tool_call.get("function_call", tool_call)
        tool_name = function_call.get("name")
        inputs = function_call.get("args", function_call.get("arguments", {}))
        if isinstance(inputs, str):
            try:
                inputs = json.loads(inputs)
            except json.JSONDecodeError:
                inputs = {}
        return {"tool_name": tool_name, "inputs": inputs}

    def format_tool_result(
        self, result: Any, tool_call_id: Optional[str] = None
    ) -> Dict[str, Any]:
        # Gemini expects function_response parts; keep as a generic dict for client conversion.
        if not isinstance(result, str):
            try:
                content = json.dumps(result, default=str)
            except (TypeError, ValueError):
                content = str(result)
        else:
            content = result

        return {
            "role": "tool",
            "content": content,
            "tool_call_id": tool_call_id,
        }
