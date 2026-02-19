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
