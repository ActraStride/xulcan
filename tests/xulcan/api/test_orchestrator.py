"""Integration tests for orchestration API routes."""

from fastapi import status
from fastapi.testclient import TestClient

from xulcan.core.engine.orchestrator import LLMOrchestrator
from xulcan.core.llm.client import LLMAuthenticationError


def test_orchestrate_returns_401_on_provider_auth_error(
    client: TestClient, monkeypatch
):
    """Return 401 when upstream LLM credentials are invalid/expired."""

    async def _raise_auth_error(self, user_input: str) -> str:
        raise LLMAuthenticationError(provider="openai")

    monkeypatch.setattr(LLMOrchestrator, "run", _raise_auth_error)

    response = client.post(
        "/orchestrate",
        json={
            "input": "Hello",
            "core_model": "gpt-4o-mini",
            "provider": "openai",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Authentication failed for provider 'openai'" in response.json()["detail"]
