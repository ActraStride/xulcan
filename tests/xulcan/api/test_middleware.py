"""
Middleware test suite for request ID handling.

Tests verify that the middleware correctly generates or preserves
X-Request-ID headers for distributed tracing and request correlation.
"""
import uuid
from fastapi.testclient import TestClient


def test_request_id_generation(client: TestClient):
    """Verify middleware generates a valid UUID when X-Request-ID is not provided.
    
    Args:
        client: FastAPI test client fixture.
    """
    response = client.get("/health/live")
    
    assert response.status_code == 200
    req_id = response.headers.get("X-Request-ID")
    
    # Validate header exists and contains a valid UUID
    assert req_id is not None
    assert uuid.UUID(req_id)


def test_request_id_passthrough(client: TestClient):
    """Verify middleware preserves client-provided X-Request-ID headers.
    
    This ensures compatibility with upstream load balancers and API gateways
    that inject their own request identifiers.
    
    Args:
        client: FastAPI test client fixture.
    """
    custom_trace_id = "trace-abc-123"
    response = client.get(
        "/health/live", 
        headers={"X-Request-ID": custom_trace_id}
    )
    
    assert response.headers.get("X-Request-ID") == custom_trace_id