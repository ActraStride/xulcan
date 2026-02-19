"""Tool runner for executing registered tools."""

from __future__ import annotations

import inspect
import json
from typing import Any, Dict, Optional

from pydantic import ValidationError

from .base import BaseTool
from .registry import ToolRegistry


class ToolExecutionError(Exception):
    """Exception raised when tool execution fails."""


class ToolNotFoundError(Exception):
    """Exception raised when a requested tool is not found."""


class ToolValidationError(Exception):
    """Exception raised when tool input validation fails."""


class ToolRunner:
    """Runner for executing tools from a registry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def _get_tool_class(self, tool_name: str) -> type[BaseTool]:
        tool_class = self.registry.get(tool_name)
        if tool_class is None:
            raise ToolNotFoundError(f"Tool '{tool_name}' not found in registry")
        return tool_class

    def run_tool(self, tool_name: str, inputs: Dict[str, Any]) -> Any:
        tool_class = self._get_tool_class(tool_name)

        try:
            tool_instance = tool_class(**inputs)
        except ValidationError as e:
            raise ToolValidationError(
                f"Input validation failed for tool '{tool_name}': {e}"
            )
        except TypeError as e:
            raise ToolValidationError(f"Invalid inputs for tool '{tool_name}': {e}")

        try:
            result = tool_instance.run()
            if inspect.isawaitable(result):
                if hasattr(result, "close"):
                    result.close()
                elif hasattr(result, "cancel"):
                    result.cancel()
                raise ToolExecutionError(
                    f"Tool '{tool_name}' returned awaitable; use run_tool_async()"
                )
            return result
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(f"Tool '{tool_name}' execution failed: {e}")

    async def run_tool_async(self, tool_name: str, inputs: Dict[str, Any]) -> Any:
        tool_class = self._get_tool_class(tool_name)

        try:
            tool_instance = tool_class(**inputs)
        except ValidationError as e:
            raise ToolValidationError(
                f"Input validation failed for tool '{tool_name}': {e}"
            )
        except TypeError as e:
            raise ToolValidationError(f"Invalid inputs for tool '{tool_name}': {e}")

        try:
            result = tool_instance.run()
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as e:
            raise ToolExecutionError(f"Tool '{tool_name}' execution failed: {e}")

    def run_tool_from_json(self, tool_name: str, inputs_json: str) -> Any:
        try:
            inputs = json.loads(inputs_json)
        except json.JSONDecodeError as e:
            raise ToolValidationError(f"Invalid JSON inputs: {e}")

        return self.run_tool(tool_name, inputs)

    def run_tool_safe(self, tool_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = self.run_tool(tool_name, inputs)
            return {"success": True, "result": result, "error": None}
        except (ToolNotFoundError, ToolValidationError, ToolExecutionError) as e:
            return {"success": False, "result": None, "error": str(e)}

    async def run_tool_safe_async(
        self, tool_name: str, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            result = await self.run_tool_async(tool_name, inputs)
            return {"success": True, "result": result, "error": None}
        except (ToolNotFoundError, ToolValidationError, ToolExecutionError) as e:
            return {"success": False, "result": None, "error": str(e)}

    def validate_tool_inputs(self, tool_name: str, inputs: Dict[str, Any]) -> bool:
        tool_class = self._get_tool_class(tool_name)
        try:
            tool_class(**inputs)
            return True
        except (ValidationError, TypeError):
            return False

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        return self.registry.get_schema(tool_name)

    def list_available_tools(self) -> Dict[str, Dict[str, Any]]:
        tools = {}
        for tool_name in self.registry.list():
            schema = self.get_tool_schema(tool_name)
            if schema:
                tools[tool_name] = schema
        return tools

    def create_tool_instance(self, tool_name: str, inputs: Dict[str, Any]) -> BaseTool:
        tool_class = self._get_tool_class(tool_name)
        try:
            return tool_class(**inputs)
        except ValidationError as e:
            raise ToolValidationError(
                f"Input validation failed for tool '{tool_name}': {e}"
            )
        except TypeError as e:
            raise ToolValidationError(f"Invalid inputs for tool '{tool_name}': {e}")

    def __repr__(self) -> str:
        return f"ToolRunner(registry={self.registry})"
