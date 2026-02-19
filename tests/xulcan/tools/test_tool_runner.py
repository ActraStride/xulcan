import pytest

from xulcan.tools.base import BaseTool, tool
from xulcan.tools.registry import ToolRegistry
from xulcan.tools.runner import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolRunner,
    ToolValidationError,
)


@tool
class EchoTool(BaseTool):
    """Echo back the provided text."""

    text: str

    def run(self):
        return f"echo:{self.text}"


@tool
class AsyncTool(BaseTool):
    """Return a value asynchronously."""

    value: int

    async def run(self):
        return self.value + 1


def test_run_tool_success():
    registry = ToolRegistry()
    registry.register(EchoTool)
    runner = ToolRunner(registry)

    result = runner.run_tool("EchoTool", {"text": "hi"})

    assert result == "echo:hi"


def test_run_tool_missing_tool():
    registry = ToolRegistry()
    runner = ToolRunner(registry)

    with pytest.raises(ToolNotFoundError):
        runner.run_tool("MissingTool", {"text": "hi"})


def test_run_tool_validation_error():
    registry = ToolRegistry()
    registry.register(EchoTool)
    runner = ToolRunner(registry)

    with pytest.raises(ToolValidationError):
        runner.run_tool("EchoTool", {"missing": "value"})


def test_run_tool_async_in_sync_path():
    registry = ToolRegistry()
    registry.register(AsyncTool)
    runner = ToolRunner(registry)

    with pytest.raises(ToolExecutionError):
        runner.run_tool("AsyncTool", {"value": 1})


@pytest.mark.asyncio
async def test_run_tool_async_success():
    registry = ToolRegistry()
    registry.register(AsyncTool)
    runner = ToolRunner(registry)

    result = await runner.run_tool_async("AsyncTool", {"value": 2})

    assert result == 3
