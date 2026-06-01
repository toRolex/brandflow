import pytest
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


def test_thumbnail_endpoint_exists():
    app = create_app()
    client = TestClient(app)
    response = client.get("/api/assets/nonexistent/thumbnail")
    assert response.status_code == 404
    assert "asset not found" in response.json().get("detail", "")