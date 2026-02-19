from xulcan.config import Settings
from xulcan.core.llm.client import LLMClientFactory, OpenAIClient


def test_factory_builds_openrouter_client():
    settings = Settings(
        OPENROUTER_API_KEY="sk-or-test",
        OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
        _env_file=None,
    )

    factory = LLMClientFactory(settings)
    client = factory.get_client("openrouter")

    assert isinstance(client, OpenAIClient)
    assert client.provider == "openrouter"


def test_factory_builds_deepseek_client():
    settings = Settings(
        DEEPSEEK_API_KEY="sk-deepseek-test",
        DEEPSEEK_BASE_URL="https://api.deepseek.com",
        _env_file=None,
    )

    factory = LLMClientFactory(settings)
    client = factory.get_client("deepseek")

    assert isinstance(client, OpenAIClient)
    assert client.provider == "deepseek"


def test_factory_create_client_uses_provider_from_config():
    settings = Settings(
        OPENAI_API_KEY="sk-openai-test",
        _env_file=None,
    )

    factory = LLMClientFactory(settings)
    client = factory.create_client({"provider": "openai"})

    assert isinstance(client, OpenAIClient)
    assert client.provider == "openai"
