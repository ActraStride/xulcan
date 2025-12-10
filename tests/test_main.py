"""Health endpoint integration tests.

Test suite for application health check endpoints including liveness probes,
readiness probes, and legacy health endpoints used for container orchestration.
"""
from fastapi import status
from fastapi.testclient import TestClient
from app.main import app


def test_liveness_probe_returns_200(client: TestClient):
    """Verify liveness probe returns 200 OK when process is running.
    
    The liveness endpoint should always return 200 if the application process
    is alive, regardless of the application's internal state.
    
    Args:
        client: FastAPI test client fixture.
    """
    response = client.get("/health/live")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "alive"}


def test_readiness_probe_happy_path(client: TestClient):
    """Verify readiness probe returns 200 OK when application is ready.
    
    The readiness endpoint should return 200 when app.state.is_ready is True,
    indicating all dependencies are initialized and the application can
    handle requests.
    
    Args:
        client: FastAPI test client fixture with is_ready set to True.
    """
    response = client.get("/health/ready")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ready"}


def test_readiness_probe_unhealthy_state(client: TestClient, monkeypatch):
    """Verify readiness probe returns 503 when application is not ready.

    Simulate an incomplete startup or dependency failure by mocking
    is_ready to False. The endpoint should return 503 Service Unavailable.

    Args:
        client: FastAPI test client fixture.
        monkeypatch: pytest fixture for patching attributes.
    """
    monkeypatch.setattr(app.state, "is_ready", False)
    response = client.get("/health/ready")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "System is starting up" in response.json()["detail"]


def test_legacy_health_deprecation(client: TestClient):
    """Verify legacy health endpoint returns deprecation notice.
    
    The /health endpoint is maintained for backward compatibility but should
    include a deprecation notice directing clients to use /health/live or
    /health/ready instead.
    
    Args:
        client: FastAPI test client fixture.
    """
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert "deprecated" in response.json().get("note", "").lower()