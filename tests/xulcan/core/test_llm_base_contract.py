import inspect

import pytest

from xulcan.core.llm.base import BaseLLMAdapter
from xulcan.core.types import Message, Response, Role, ToolSpec


class DummyLLMAdapter(BaseLLMAdapter):
    async def generate_response(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        output_schema=None,
    ) -> Response:
        if messages:
            return Response(content=messages[-1].content)
        return Response(content="")

    def count_tokens(self, text: str) -> int:
        return len(text.split())


def test_base_llm_adapter_is_abstract():
    assert inspect.isabstract(BaseLLMAdapter)
    assert "generate_response" in BaseLLMAdapter.__abstractmethods__
    assert "count_tokens" in BaseLLMAdapter.__abstractmethods__


@pytest.mark.asyncio
async def test_dummy_adapter_uses_shared_models():
    adapter = DummyLLMAdapter(model_name="demo", api_key="test")
    response = await adapter.generate_response(
        [Message(role=Role.USER, content="hello world")]
    )

    assert response.content == "hello world"
    assert adapter.count_tokens("one two three") == 3


def test_base_contract_does_not_import_provider_sdks():
    source = inspect.getsource(BaseLLMAdapter)
    lowered = source.lower()
    assert "openai" not in lowered
    assert "google" not in lowered
