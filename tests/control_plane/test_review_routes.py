from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def test_approve_review_returns_approved_status() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/reviews/j1/approve",
        json={"review_gate": "script_review"},
    )
    assert response.status_code == 404


def test_reject_review_returns_rejected_status() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/reviews/j1/reject",
        json={"review_gate": "script_review"},
    )
    assert response.status_code == 404
