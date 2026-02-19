"""Tool registry for managing and discovering tools."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Type

from .base import BaseTool


class ToolRegistry:
    """Registry for managing and discovering tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, Type[BaseTool]] = {}

    def register(self, tool_class: Type[BaseTool], name: Optional[str] = None) -> None:
        if not issubclass(tool_class, BaseTool):
            raise TypeError(f"Tool {tool_class.__name__} must inherit from BaseTool")

        tool_name = name or tool_class.get_name()
        if tool_name in self._tools:
            raise ValueError(f"Tool '{tool_name}' is already registered")

        self._tools[tool_name] = tool_class

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Optional[Type[BaseTool]]:
        return self._tools.get(name)

    def list(self) -> List[str]:
        return list(self._tools.keys())

    def list_tools(self) -> Dict[str, Type[BaseTool]]:
        return self._tools.copy()

    def clear(self) -> None:
        self._tools.clear()

    def size(self) -> int:
        return len(self._tools)

    def contains(self, name: str) -> bool:
        return name in self._tools

    def export_schemas(self) -> List[Dict[str, Any]]:
        return [tool_class.get_schema() for tool_class in self._tools.values()]

    def get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        tool_class = self.get(name)
        return tool_class.get_schema() if tool_class else None

    def auto_discover(self, module: Any) -> int:
        discovered = 0
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseTool)
                and obj is not BaseTool
                and getattr(obj, "_is_xulcan_tool", False)
            ):
                try:
                    self.register(obj)
                    discovered += 1
                except ValueError:
                    pass
        return discovered

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self) -> Iterator[str]:
        return iter(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistry({len(self._tools)} tools: {list(self._tools.keys())})"
