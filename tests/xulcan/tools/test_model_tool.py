import pytest

from xulcan.core.llm.client import BaseLLMClient, LLMResponse
from xulcan.core.llm.adapters.openai import OpenAIAdapter
from xulcan.tools.models import ModelRegistry, ModelSpec, ModelTool
from xulcan.tools.registry import ToolRegistry


class DummySubClient(BaseLLMClient):
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
        return LLMResponse(content="sub-response", tool_calls=[])


class DummyFactory:
    def __init__(self):
        self.client = DummySubClient()

    def get_client(self, provider: str) -> BaseLLMClient:
        return self.client


@pytest.mark.asyncio
async def test_model_tool_runs_sub_model():
    tool_registry = ToolRegistry()
    model_registry = ModelRegistry()
    model_registry.register(
        ModelSpec(name="sub", provider="openai", model_id="gpt-4o-mini")
    )

    ModelTool.configure(
        model_registry=model_registry,
        tool_registry=tool_registry,
        client_factory=DummyFactory(),
        adapters={"openai": OpenAIAdapter()},
    )

    tool = ModelTool(model="sub", prompt="hello")
    result = await tool.run()

    assert result["output"] == "sub-response"
    assert result["model"] == "sub"


def test_model_spec_accepts_openrouter_provider():
    spec = ModelSpec(
        name="sub-openrouter",
        provider="openrouter",
        model_id="openai/gpt-4o-mini",
    )
    assert spec.provider == "openrouter"
