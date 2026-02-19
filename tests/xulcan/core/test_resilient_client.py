import pytest

from xulcan.core.llm.client import (
    BaseLLMClient,
    LLMProviderError,
    LLMResponse,
    LLMValidationError,
)
from xulcan.core.llm.resilience import (
    AllProvidersFailedError,
    ProviderCandidate,
    ResilientClient,
)


class StaticClient(BaseLLMClient):
    def __init__(self, response: LLMResponse) -> None:
        self.response = response
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
        return self.response


class FailingClient(BaseLLMClient):
    def __init__(self, error: Exception) -> None:
        self.error = error
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
        raise self.error


class StubFactory:
    def __init__(self, clients):
        self.clients = clients

    def get_client(self, provider: str):
        return self.clients[provider]


@pytest.mark.asyncio
async def test_resilient_client_falls_back_on_provider_error():
    primary = FailingClient(LLMProviderError(provider="openai", message="timeout"))
    backup = StaticClient(LLMResponse(content="ok", tool_calls=[]))

    resilient = ResilientClient(
        factory=StubFactory({"openai": primary, "openrouter": backup}),
        candidates=["openai", "openrouter"],
    )

    response = await resilient.create_chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        tool_choice=None,
        temperature=0.0,
        max_tokens=100,
        model="demo-model",
    )

    assert response.content == "ok"
    assert primary.calls == 1
    assert backup.calls == 1


@pytest.mark.asyncio
async def test_resilient_client_falls_back_on_validation_error():
    primary = FailingClient(
        LLMValidationError(provider="gemini", message="bad response shape")
    )
    backup = StaticClient(LLMResponse(content="from backup", tool_calls=[]))

    resilient = ResilientClient(
        factory=StubFactory({"gemini": primary, "openai": backup}),
        candidates=["gemini", "openai"],
    )

    response = await resilient.create_chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        tool_choice=None,
        temperature=0.0,
        max_tokens=100,
        model="demo-model",
    )

    assert response.content == "from backup"
    assert primary.calls == 1
    assert backup.calls == 1


@pytest.mark.asyncio
async def test_resilient_client_raises_when_all_providers_fail():
    openai_client = FailingClient(
        LLMProviderError(provider="openai", message="rate limit")
    )
    gemini_client = FailingClient(
        LLMValidationError(provider="gemini", message="missing candidates")
    )

    resilient = ResilientClient(
        factory=StubFactory({"openai": openai_client, "gemini": gemini_client}),
        candidates=[
            ProviderCandidate(provider="openai"),
            ProviderCandidate(provider="gemini"),
        ],
    )

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await resilient.create_chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            tools=None,
            tool_choice=None,
            temperature=0.0,
            max_tokens=100,
            model="demo-model",
        )

    assert exc_info.value.providers == ["openai", "gemini"]
    assert len(exc_info.value.errors) == 2
