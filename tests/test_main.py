from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    """Verify that the `/health` endpoint exposes the service baseline."""
    response = client.get("/health")
    assert response.status_code == 200
    # Keep this contract aligned with the implementation in app/main.py.
    assert response.json() == {"status": "ok"}