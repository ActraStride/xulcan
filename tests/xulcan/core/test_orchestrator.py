import pytest

from xulcan.core.engine.orchestrator import LLMOrchestrator, OrchestratorConfig
from xulcan.core.engine.policies import OrchestrationPolicy
from xulcan.core.llm.adapters.openai import OpenAIAdapter
from xulcan.core.llm.client import BaseLLMClient, LLMResponse
from xulcan.tools.base import BaseTool, tool
from xulcan.tools.registry import ToolRegistry


@tool
class EchoTool(BaseTool):
    """Echo back the provided text."""

    text: str

    def run(self):
        return f"echo:{self.text}"


class DummyClient(BaseLLMClient):
    def __init__(self):
        self.calls = 0

    async def create_chat_completion(
        self,
        *,
        messages,
        tools,
        tool_choice,
        temperature,
        max_tokens,
        model,
    ) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "EchoTool",
                            "arguments": '{"text": "hi"}',
                        },
                    }
                ],
            )
        return LLMResponse(content="done", tool_calls=[])


@pytest.mark.asyncio
async def test_orchestrator_runs_tool_and_returns_final_response():
    registry = ToolRegistry()
    registry.register(EchoTool)

    orchestrator = LLMOrchestrator(
        llm_client=DummyClient(),
        registry=registry,
        adapter=OpenAIAdapter(),
        model="gpt-4o-mini",
        policy=OrchestrationPolicy(max_iterations=3),
        config=OrchestratorConfig(temperature=0.0, max_tokens=256),
    )

    output = await orchestrator.run("say hi")

    assert output == "done"
    assert orchestrator.last_tool_results
    assert orchestrator.last_tool_results[0]["tool"] == "EchoTool"
    assert orchestrator.last_tool_results[0]["result"] == "echo:hi"
