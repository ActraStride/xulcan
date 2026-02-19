"""Base adapter class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from xulcan.tools.registry import ToolRegistry
from xulcan.tools.base import BaseTool


class BaseAdapter(ABC):
    """Base class for LLM adapters."""

    @abstractmethod
    def export_tools(self, registry: ToolRegistry) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def export_tool(self, tool_class: type[BaseTool]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def convert_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Convert LLM tool call to {tool_name, inputs}."""
        pass

    @abstractmethod
    def format_tool_result(
        self, result: Any, tool_call_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Format a tool result as a provider-specific message."""
        pass

    def create_system_prompt(
        self, registry: ToolRegistry, custom_instructions: Optional[str] = None
    ) -> str:
        tools = registry.list_tools()

        prompt_parts: List[str] = []
        if custom_instructions:
            prompt_parts.append(custom_instructions)
            prompt_parts.append("")

        if tools:
            prompt_parts.append("You have access to the following tools:")
            prompt_parts.append("")
            for tool_name, tool_class in tools.items():
                description = tool_class.get_description()
                prompt_parts.append(f"- {tool_name}: {description}")
            prompt_parts.append("")
            prompt_parts.append(
                "Use these tools when appropriate to help answer questions or complete tasks. "
                "Call tools with the correct parameters based on their schemas."
            )
        else:
            prompt_parts.append("No tools are currently available.")

        return "\n".join(prompt_parts)
