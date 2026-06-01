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


def test_resume_from_phase_returns_queued_for_retry() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/jobs/j1/resume-from-phase",
        json={"phase": "video_burn"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "j1"
    assert data["phase"] == "video_burn"
    assert data["status"] == "queued_for_retry"


def test_job_detail_html_returns_minimal_page() -> None:
    client = TestClient(create_app())
    response = client.get("/jobs/j1")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "j1" in response.text


def test_review_detail_html_returns_minimal_page() -> None:
    client = TestClient(create_app())
    response = client.get("/api/reviews/j1")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "j1" in response.text
