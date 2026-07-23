"""Tests for review route phase-gating (#260)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app

# Non-review pipeline phases (all phases except the four review gates).
NON_REVIEW_PHASES = [
    "queued",
    "script_generating",
    "tts_generating",
    "subtitle_generating",
    "asset_retrieving",
    "montage_assembling",
    "video_rendering",
    "final_rendering",
    "scene_assembling",
]

TERMINAL_NON_REVIEW = [
    "failed",
    "cancelled",
    "paused",
]

REVIEW_PHASES_LIST = ["script_review", "tts_review", "asset_review", "final_review"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_job(
    tmp_path: Path,
    job_id: str,
    phase: str,
    review_status: str = "pending",
    mode: str = "generate",
) -> dict[str, str]:
    """Create a minimal job record on disk under *tmp_path*."""
    project_id = "proj-001"
    control_dir = tmp_path / "workspace" / "projects" / project_id / "control" / "jobs"
    control_dir.mkdir(parents=True, exist_ok=True)
    job_json = control_dir / f"{job_id}.json"
    job_json.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "project_id": project_id,
                "product": "test-product",
                "phase": phase,
                "review_status": review_status,
                "mode": mode,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"project_id": project_id, "job_id": job_id}


def _create_runtime_job_dir(tmp_path: Path, project_id: str, job_id: str) -> Path:
    """Create the runtime job directory so asset_review approve can locate it."""
    job_dir = (
        tmp_path / "workspace" / "projects" / project_id / "runtime" / "jobs" / job_id
    )
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def _read_job_phase(tmp_path: Path, job_id: str) -> str:
    """Return the persisted phase for *job_id* (searches all projects)."""
    projects_root = tmp_path / "workspace" / "projects"
    for proj_dir in projects_root.iterdir():
        if not proj_dir.is_dir():
            continue
        control_dir = proj_dir / "control" / "jobs"
        job_path = control_dir / f"{job_id}.json"
        if job_path.exists():
            data = json.loads(job_path.read_text(encoding="utf-8"))
            return data.get("phase", "")
    return ""


# ---------------------------------------------------------------------------
# Existing smoke tests (job does not exist → 404)
# ---------------------------------------------------------------------------


def test_approve_review_returns_approved_status() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/reviews/j1/approve",
            json={"review_gate": "script_review"},
        )
        assert response.status_code == 404


def test_reject_review_returns_rejected_status() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/reviews/j1/reject",
            json={"review_gate": "script_review"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Approve – non-review phase → 409
# ---------------------------------------------------------------------------


class TestApproveNonReviewPhase:
    @pytest.mark.parametrize("phase", NON_REVIEW_PHASES + TERMINAL_NON_REVIEW)
    def test_returns_409_phase_info(self, tmp_path: Path, phase: str) -> None:
        _create_job(tmp_path, "j-app", phase, review_status="pending")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/reviews/j-app/approve",
                json={"review_gate": phase},
            )
            assert resp.status_code == 409
            detail = resp.json()["detail"]
            assert "not in a review phase" in detail.lower()
            assert phase in detail

    @pytest.mark.parametrize("phase", NON_REVIEW_PHASES + TERMINAL_NON_REVIEW)
    def test_does_not_modify_job_on_409(self, tmp_path: Path, phase: str) -> None:
        """A 409 approve must leave the phase and review_status unchanged."""
        _create_job(tmp_path, "j-imm", phase, review_status="pending")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            client.post(
                "/api/reviews/j-imm/approve",
                json={"review_gate": phase},
            )

            persisted_phase = _read_job_phase(tmp_path, "j-imm")
            assert persisted_phase == phase


# ---------------------------------------------------------------------------
# Reject – non-review phase → 409
# ---------------------------------------------------------------------------


class TestRejectNonReviewPhase:
    @pytest.mark.parametrize("phase", NON_REVIEW_PHASES + TERMINAL_NON_REVIEW)
    def test_returns_409_phase_info(self, tmp_path: Path, phase: str) -> None:
        _create_job(tmp_path, "j-rej", phase, review_status="pending")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/reviews/j-rej/reject",
                json={"review_gate": phase},
            )
            assert resp.status_code == 409
            detail = resp.json()["detail"]
            assert "not in a review phase" in detail.lower()
            assert phase in detail

    @pytest.mark.parametrize("phase", NON_REVIEW_PHASES + TERMINAL_NON_REVIEW)
    def test_does_not_modify_job_on_409(self, tmp_path: Path, phase: str) -> None:
        """A 409 reject must leave the phase unchanged."""
        _create_job(tmp_path, "j-imm2", phase, review_status="pending")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            client.post(
                "/api/reviews/j-imm2/reject",
                json={"review_gate": phase},
            )

            persisted_phase = _read_job_phase(tmp_path, "j-imm2")
            assert persisted_phase == phase


# ---------------------------------------------------------------------------
# Completed phase → 409 (explicitly rejected)
# ---------------------------------------------------------------------------


class TestCompletedPhase:
    def test_approve_from_completed_returns_409(self, tmp_path: Path) -> None:
        _create_job(tmp_path, "j-done", "completed", review_status="approved")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/reviews/j-done/approve",
                json={"review_gate": "completed"},
            )
            assert resp.status_code == 409
            assert "not in a review phase" in resp.json()["detail"].lower()

    def test_reject_from_completed_returns_409(self, tmp_path: Path) -> None:
        _create_job(tmp_path, "j-done2", "completed", review_status="approved")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/reviews/j-done2/reject",
                json={"review_gate": "completed"},
            )
            assert resp.status_code == 409
            assert "not in a review phase" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Gate mismatch – review phase but wrong gate → 409
# ---------------------------------------------------------------------------


class TestGateMismatch:
    def test_approve_gate_mismatch_returns_409(self, tmp_path: Path) -> None:
        _create_job(tmp_path, "j-mm", "script_review", review_status="pending")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/reviews/j-mm/approve",
                json={"review_gate": "tts_review"},
            )
            assert resp.status_code == 409
            detail = resp.json()["detail"]
            assert "gate mismatch" in detail.lower()
            assert "script_review" in detail
            assert "tts_review" in detail

    def test_reject_gate_mismatch_returns_409(self, tmp_path: Path) -> None:
        _create_job(tmp_path, "j-mm2", "asset_review", review_status="pending")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/reviews/j-mm2/reject",
                json={"review_gate": "final_review"},
            )
            assert resp.status_code == 409
            detail = resp.json()["detail"]
            assert "gate mismatch" in detail.lower()
            assert "asset_review" in detail
            assert "final_review" in detail

    def test_gate_mismatch_does_not_modify_job(self, tmp_path: Path) -> None:
        _create_job(tmp_path, "j-mm3", "script_review", review_status="pending")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            client.post(
                "/api/reviews/j-mm3/approve",
                json={"review_gate": "tts_review"},
            )

            persisted_phase = _read_job_phase(tmp_path, "j-mm3")
            assert persisted_phase == "script_review"


# ---------------------------------------------------------------------------
# Approve success – all four review phases
# ---------------------------------------------------------------------------


class TestApproveSuccess:
    @pytest.mark.parametrize(
        "phase,expected_next",
        [
            ("script_review", "tts_generating"),
            ("tts_review", "subtitle_generating"),
            ("asset_review", "montage_assembling"),
            ("final_review", "completed"),
        ],
    )
    def test_approve_advances_phase(
        self, tmp_path: Path, phase: str, expected_next: str
    ) -> None:
        ctx = _create_job(tmp_path, f"j-ok-{phase}", phase, review_status="pending")
        # asset_review needs a runtime job dir so _find_job_dir does not 404
        if phase == "asset_review":
            _create_runtime_job_dir(tmp_path, ctx["project_id"], f"j-ok-{phase}")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/j-ok-{phase}/approve",
                json={"review_gate": phase},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "approved"
            assert data["next_phase"] == expected_next

            # Verify the job was actually advanced on disk
            persisted_phase = _read_job_phase(tmp_path, f"j-ok-{phase}")
            assert persisted_phase == expected_next


# ---------------------------------------------------------------------------
# Reject success – all four review phases
# ---------------------------------------------------------------------------


class TestRejectSuccess:
    @pytest.mark.parametrize(
        "phase,expected_reject_target",
        [
            ("script_review", "script_generating"),
            ("tts_review", "tts_generating"),
            ("asset_review", "asset_retrieving"),
            ("final_review", "video_rendering"),
        ],
    )
    def test_reject_reverts_phase(
        self, tmp_path: Path, phase: str, expected_reject_target: str
    ) -> None:
        _create_job(tmp_path, f"j-rj-{phase}", phase, review_status="pending")
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/j-rj-{phase}/reject",
                json={"review_gate": phase},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "rejected"
            assert data["next_phase"] == expected_reject_target

            # Verify the job was actually reverted on disk
            persisted_phase = _read_job_phase(tmp_path, f"j-rj-{phase}")
            assert persisted_phase == expected_reject_target


# ---------------------------------------------------------------------------
# Import mode – review phases behave correctly
# ---------------------------------------------------------------------------


class TestImportMode:
    def test_approve_import_script_review_succeeds(self, tmp_path: Path) -> None:
        """Import-mode jobs should still be able to approve a genuine review
        gate (even though import mode normally skips script_review)."""
        _create_job(
            tmp_path,
            "j-imp",
            "script_review",
            review_status="pending",
            mode="import",
        )
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/reviews/j-imp/approve",
                json={"review_gate": "script_review"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "approved"
            assert data["next_phase"] == "tts_generating"

    def test_reject_import_script_review_succeeds(self, tmp_path: Path) -> None:
        _create_job(
            tmp_path,
            "j-imp2",
            "script_review",
            review_status="pending",
            mode="import",
        )
        app = create_app(root_dir=tmp_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/reviews/j-imp2/reject",
                json={"review_gate": "script_review"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "rejected"


# ---------------------------------------------------------------------------
# Verify REVIEW_PHASES lives in domain_core and is importable
# ---------------------------------------------------------------------------


def test_review_phases_defined_in_domain_core() -> None:
    """REVIEW_PHASES must be importable from domain_core.models."""
    from packages.domain_core.models import REVIEW_PHASES as rp

    assert isinstance(rp, frozenset)
    assert rp == {"script_review", "tts_review", "asset_review", "final_review"}
