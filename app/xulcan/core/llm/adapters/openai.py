"""OpenAI adapter for Xulcan tools."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import BaseAdapter
from xulcan.tools.registry import ToolRegistry
from xulcan.tools.base import BaseTool


class OpenAIAdapter(BaseAdapter):
    """Adapter for OpenAI tool calling format."""

    def export_tools(self, registry: ToolRegistry) -> List[Dict[str, Any]]:
        return registry.export_schemas()

    def export_tool(self, tool_class: type[BaseTool]) -> Dict[str, Any]:
        return tool_class.get_schema()

    def convert_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        function = tool_call.get("function", {})
        tool_name = function.get("name")

        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        return {"tool_name": tool_name, "inputs": arguments}

    def format_tool_result(
        self, result: Any, tool_call_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not isinstance(result, str):
            try:
                content = json.dumps(result, default=str)
            except (TypeError, ValueError):
                content = str(result)
        else:
            content = result

        response: Dict[str, Any] = {"role": "tool", "content": content}
        if tool_call_id:
            response["tool_call_id"] = tool_call_id
        return response
