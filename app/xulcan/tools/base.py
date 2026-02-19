"""Base tool definitions and decorators for Xulcan."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Type, TypeVar, get_type_hints
import inspect

from pydantic import BaseModel, create_model

T = TypeVar("T", bound="BaseTool")


class BaseTool(BaseModel, ABC):
    """Base class for all tools.

    Tools define typed inputs and implement a run method
    to execute the tool's logic.
    """

    @abstractmethod
    def run(self) -> Any:
        """Execute the tool's logic."""
        raise NotImplementedError

    @classmethod
    def get_name(cls) -> str:
        """Return the tool name (class name by default)."""
        return cls.__name__

    @classmethod
    def get_description(cls) -> str:
        """Return the tool description from docstring."""
        return cls.__doc__ or f"Tool: {cls.get_name()}"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the tool JSON schema in OpenAI function format."""
        schema = cls.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": cls.get_name(),
                "description": cls.get_description(),
                "parameters": schema,
            },
        }


def tool(cls: Type[T]) -> Type[T]:
    """Decorator to register a class as a tool.

    Ensures the class inherits from BaseTool and implements run().
    """
    if not issubclass(cls, BaseTool):
        raise TypeError(f"Tool {cls.__name__} must inherit from BaseTool")

    if not hasattr(cls, "run") or cls.run is BaseTool.run:
        raise TypeError(f"Tool {cls.__name__} must implement run()")

    setattr(cls, "_is_xulcan_tool", True)
    return cls


def create_tool_from_function(
    func: Callable[..., Any],
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Type[BaseTool]:
    """Create a Tool class from a regular function."""
    if not hasattr(func, "__name__"):
        raise ValueError("Function must have a __name__ attribute")

    tool_name = name or func.__name__
    tool_description = description or (func.__doc__ or f"Tool: {tool_name}")

    sig = inspect.signature(func)
    type_hints = get_type_hints(func)

    fields: Dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        param_type = type_hints.get(param_name, Any)
        if param.default is not inspect.Parameter.empty:
            fields[param_name] = (param_type, param.default)
        else:
            fields[param_name] = (param_type, ...)

    def run_method(self: BaseTool) -> Any:
        kwargs = {name: getattr(self, name) for name in fields.keys()}
        return func(**kwargs)

    tool_class = create_model(tool_name, __base__=BaseTool, **fields)
    setattr(tool_class, "run", run_method)
    tool_class.__doc__ = tool_description
    setattr(tool_class, "_is_xulcan_tool", True)

    return tool_class
