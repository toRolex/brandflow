import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


@pytest.mark.e2e
def test_root_serves_frontend() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/")
        assert response.status_code == 200
