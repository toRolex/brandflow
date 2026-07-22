from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


def test_thumbnail_endpoint_exists():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/assets/nonexistent/thumbnail")
        assert response.status_code == 404
