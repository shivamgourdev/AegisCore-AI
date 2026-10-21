"""Backend tests — real functional coverage for Phase 1–2.

The previous test_placeholder.py asserted `True` (no functional coverage).
This file replaces it with tests that exercise the actual FastAPI application.
"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint_returns_200():
    """GET /health must return HTTP 200 with a JSON status body."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "AegisCore AI"


def test_health_endpoint_response_shape():
    """The health response must contain exactly the expected fields."""
    response = client.get("/health")
    body = response.json()
    assert set(body.keys()) == {"status", "service"}


def test_app_is_importable_and_routes_registered():
    """The FastAPI app must be importable and have the /health route registered."""
    assert app is not None
    paths = []
    for route in app.routes:
        if hasattr(route, "path"):
            paths.append(route.path)
        elif hasattr(route, "routes"):
            for r in route.routes:
                if hasattr(r, "path"):
                    paths.append(r.path)
    assert "/health" in paths
    assert "/openapi.json" in paths


def test_health_route_returns_json_content_type():
    """The /health endpoint must set Content-Type to application/json."""
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]
