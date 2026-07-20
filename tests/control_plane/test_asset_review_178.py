"""Tests for asset review API — set-blank, set-asset, re-search, restore, approve."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _setup_job(tmp_path: Path, clips: list[dict]) -> dict:
    """Create a fake job with selected_clips.json and return {project_id, job_id, root_dir}."""
    root_dir = tmp_path
    project_id = "proj-001"
    job_id = "test-job-178"

    job_dir = (
        root_dir / "workspace" / "projects" / project_id / "runtime" / "jobs" / job_id
    )
    job_dir.mkdir(parents=True, exist_ok=True)
    clips_path = job_dir / "selected_clips.json"
    clips_path.write_text(
        json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    control_dir = root_dir / "workspace" / "projects" / project_id / "control" / "jobs"
    control_dir.mkdir(parents=True, exist_ok=True)
    job_json = control_dir / f"{job_id}.json"
    job_json.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "project_id": project_id,
                "product": "羊肚菌",
                "phase": "asset_review",
                "review_status": "pending",
                "mode": "generate",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {"tmp_path": tmp_path, "project_id": project_id, "job_id": job_id}


CLIP_SAMPLE = [
    {
        "sentence": "第一句介绍。",
        "category": "intro",
        "file_path": "/data/clip1.mp4",
        "asset_id": "a1",
        "duration_seconds": 5.0,
        "method": "llm_match",
        "visual_type": "clip",
    },
    {
        "sentence": "第二句详情。",
        "category": "detail",
        "file_path": "",
        "asset_id": "",
        "duration_seconds": 0.0,
        "method": "",
        "visual_type": "unresolved",
    },
    {
        "sentence": "第三句结尾。",
        "category": "outro",
        "file_path": "/data/clip3.mp4",
        "asset_id": "a3",
        "duration_seconds": 3.0,
        "method": "llm_match",
        "visual_type": "clip",
    },
]


class TestSetBlank:
    def test_set_clip_to_blank(self, tmp_path: Path) -> None:
        ctx = _setup_job(tmp_path, CLIP_SAMPLE)
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/set-blank",
            json={"clip_index": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "set_blank"
        assert data["clip_index"] == 0

        clips_path = (
            ctx["tmp_path"]
            / "workspace"
            / "projects"
            / ctx["project_id"]
            / "runtime"
            / "jobs"
            / ctx["job_id"]
            / "selected_clips.json"
        )
        clips = json.loads(clips_path.read_text(encoding="utf-8"))
        assert clips[0]["visual_type"] == "blank"
        assert clips[0]["file_path"] == ""
        assert clips[0]["asset_id"] == ""

    def test_set_blank_invalid_index(self, tmp_path: Path) -> None:
        ctx = _setup_job(tmp_path, CLIP_SAMPLE)
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/set-blank",
            json={"clip_index": 99},
        )
        assert resp.status_code == 400

    def test_set_blank_on_already_blank_is_idempotent(self, tmp_path: Path) -> None:
        ctx = _setup_job(
            tmp_path,
            [
                {
                    "sentence": "空白句。",
                    "visual_type": "blank",
                    "file_path": "",
                    "asset_id": "",
                },
            ],
        )
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/set-blank",
            json={"clip_index": 0},
        )
        assert resp.status_code == 200


class TestSetAsset:
    def test_set_clip_to_asset(self, tmp_path: Path) -> None:
        ctx = _setup_job(
            tmp_path,
            [
                {
                    "sentence": "初始 unresolved。",
                    "visual_type": "unresolved",
                    "file_path": "",
                    "asset_id": "",
                },
            ],
        )
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/set-asset",
            json={
                "clip_index": 0,
                "file_path": "/data/new_clip.mp4",
                "asset_id": "a-new",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "set_asset"
        assert data["visual_type"] == "clip"

        clips_path = (
            ctx["tmp_path"]
            / "workspace"
            / "projects"
            / ctx["project_id"]
            / "runtime"
            / "jobs"
            / ctx["job_id"]
            / "selected_clips.json"
        )
        clips = json.loads(clips_path.read_text(encoding="utf-8"))
        assert clips[0]["visual_type"] == "clip"
        assert clips[0]["file_path"] == "/data/new_clip.mp4"
        assert clips[0]["asset_id"] == "a-new"


class TestReSearch:
    def test_re_search_updates_with_new_asset(self, tmp_path: Path) -> None:
        ctx = _setup_job(
            tmp_path,
            [
                {
                    "sentence": "重新搜索这句。",
                    "category": "intro",
                    "visual_type": "unresolved",
                    "file_path": "",
                    "asset_id": "",
                    "method": "",
                },
            ],
        )
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/re-search",
            json={"clip_index": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "re_searched"

    def test_re_search_does_not_overwrite_blank(self, tmp_path: Path) -> None:
        """Re-search should not change a clip that is already explicitly set to blank."""
        ctx = _setup_job(
            tmp_path,
            [
                {
                    "sentence": "已是空白。",
                    "category": "",
                    "visual_type": "blank",
                    "file_path": "",
                    "asset_id": "",
                    "method": "manual",
                },
            ],
        )
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/re-search",
            json={"clip_index": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "re_searched"
        assert data["visual_type"] == "blank"  # unchanged


class TestRestore:
    def test_restore_original_asset(self, tmp_path: Path) -> None:
        clips = [
            {
                "sentence": "第一句。",
                "category": "intro",
                "file_path": "/data/original.mp4",
                "asset_id": "a-orig",
                "duration_seconds": 5.0,
                "method": "llm_match",
                "visual_type": "clip",
            },
        ]
        ctx = _setup_job(tmp_path, clips)
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        # First, set to blank
        client.post(
            f"/api/reviews/{ctx['job_id']}/asset/set-blank", json={"clip_index": 0}
        )

        # Then restore
        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/restore",
            json={"clip_index": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "restored"

        clips_path = (
            ctx["tmp_path"]
            / "workspace"
            / "projects"
            / ctx["project_id"]
            / "runtime"
            / "jobs"
            / ctx["job_id"]
            / "selected_clips.json"
        )
        clips = json.loads(clips_path.read_text(encoding="utf-8"))
        assert clips[0]["visual_type"] == "clip"
        assert clips[0]["file_path"] == "/data/original.mp4"
        assert clips[0]["asset_id"] == "a-orig"


class TestApprove:
    def test_approve_blocks_unresolved(self, tmp_path: Path) -> None:
        ctx = _setup_job(tmp_path, CLIP_SAMPLE)  # index 1 is unresolved
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/approve",
            json={"review_gate": "asset_review"},
        )
        assert resp.status_code == 409
        detail = resp.json()
        assert "unresolved" in detail.get("detail", "").lower()

    def test_approve_all_blank_warns_but_allows_with_force(
        self, tmp_path: Path
    ) -> None:
        ctx = _setup_job(
            tmp_path,
            [
                {"sentence": "全空白一。", "visual_type": "blank"},
                {"sentence": "全空白二。", "visual_type": "blank"},
            ],
        )
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        # Without force should warn
        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/approve",
            json={"review_gate": "asset_review"},
        )
        assert resp.status_code == 409
        detail = resp.json()
        assert "blank" in detail.get("detail", "").lower()

    def test_approve_all_blank_with_force_succeeds(self, tmp_path: Path) -> None:
        ctx = _setup_job(
            tmp_path,
            [
                {"sentence": "全空白一。", "visual_type": "blank"},
                {"sentence": "全空白二。", "visual_type": "blank"},
            ],
        )
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/approve",
            json={"review_gate": "asset_review", "force": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"

    def test_approve_freeze_snapshot(self, tmp_path: Path) -> None:
        """Approval writes reviewed_assets.json and preserves asset IDs."""
        ctx = _setup_job(
            tmp_path,
            [
                {
                    "sentence": "第一句。",
                    "category": "intro",
                    "file_path": "/data/clip1.mp4",
                    "asset_id": "a1",
                    "duration_seconds": 5.0,
                    "method": "llm_match",
                    "visual_type": "clip",
                },
                {
                    "sentence": "第二句。",
                    "category": "detail",
                    "file_path": "",
                    "asset_id": "",
                    "duration_seconds": 0.0,
                    "method": "",
                    "visual_type": "blank",
                },
            ],
        )
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/approve",
            json={"review_gate": "asset_review"},
        )
        assert resp.status_code == 200

        clips_path = (
            ctx["tmp_path"]
            / "workspace"
            / "projects"
            / ctx["project_id"]
            / "runtime"
            / "jobs"
            / ctx["job_id"]
            / "reviewed_assets.json"
        )
        assert clips_path.exists()
        snapshot = json.loads(clips_path.read_text(encoding="utf-8"))
        assert len(snapshot) == 2
        assert snapshot[0]["asset_id"] == "a1"
        assert snapshot[1]["visual_type"] == "blank"

    def test_approve_approves_clean_clip_list(self, tmp_path: Path) -> None:
        ctx = _setup_job(
            tmp_path,
            [
                {
                    "sentence": "第一句。",
                    "category": "intro",
                    "file_path": "/data/clip1.mp4",
                    "asset_id": "a1",
                    "visual_type": "clip",
                },
                {
                    "sentence": "第二句。",
                    "category": "detail",
                    "file_path": "/data/clip2.mp4",
                    "asset_id": "a2",
                    "visual_type": "clip",
                },
            ],
        )
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/approve",
            json={"review_gate": "asset_review"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"


def _set_phase(tmp_path: Path, project_id: str, job_id: str, phase: str) -> None:
    """Update the job record phase in the control directory."""
    control_dir = tmp_path / "workspace" / "projects" / project_id / "control" / "jobs"
    job_json = control_dir / f"{job_id}.json"
    job_data = json.loads(job_json.read_text(encoding="utf-8"))
    job_data["phase"] = phase
    job_json.write_text(
        json.dumps(job_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class TestPhaseGating:
    """All asset mutation endpoints return 409 when job is not in asset_review phase."""

    @pytest.mark.parametrize("phase", ["queued", "script_generating", "video_rendering", "completed"])
    def test_set_blank_outside_asset_review_returns_409(self, tmp_path: Path, phase: str) -> None:
        ctx = _setup_job(tmp_path, CLIP_SAMPLE)
        _set_phase(tmp_path, ctx["project_id"], ctx["job_id"], phase)
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/set-blank",
            json={"clip_index": 0},
        )
        assert resp.status_code == 409
        assert "asset_review" in resp.json()["detail"].lower()

    @pytest.mark.parametrize("phase", ["queued", "script_generating", "video_rendering", "completed"])
    def test_set_asset_outside_asset_review_returns_409(self, tmp_path: Path, phase: str) -> None:
        ctx = _setup_job(tmp_path, CLIP_SAMPLE)
        _set_phase(tmp_path, ctx["project_id"], ctx["job_id"], phase)
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/set-asset",
            json={"clip_index": 0, "file_path": "/data/clip.mp4", "asset_id": "a1"},
        )
        assert resp.status_code == 409
        assert "asset_review" in resp.json()["detail"].lower()

    @pytest.mark.parametrize("phase", ["queued", "script_generating", "video_rendering", "completed"])
    def test_re_search_outside_asset_review_returns_409(self, tmp_path: Path, phase: str) -> None:
        ctx = _setup_job(tmp_path, CLIP_SAMPLE)
        _set_phase(tmp_path, ctx["project_id"], ctx["job_id"], phase)
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/re-search",
            json={"clip_index": 0},
        )
        assert resp.status_code == 409
        assert "asset_review" in resp.json()["detail"].lower()

    @pytest.mark.parametrize("phase", ["queued", "script_generating", "video_rendering", "completed"])
    def test_restore_outside_asset_review_returns_409(self, tmp_path: Path, phase: str) -> None:
        ctx = _setup_job(tmp_path, CLIP_SAMPLE)
        _set_phase(tmp_path, ctx["project_id"], ctx["job_id"], phase)
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/restore",
            json={"clip_index": 0},
        )
        assert resp.status_code == 409
        assert "asset_review" in resp.json()["detail"].lower()

    def test_set_blank_in_asset_review_succeeds(self, tmp_path: Path) -> None:
        """Sanity check: the endpoint works normally when in the right phase."""
        ctx = _setup_job(tmp_path, CLIP_SAMPLE)
        app = create_app(root_dir=ctx["tmp_path"])
        client = TestClient(app)

        resp = client.post(
            f"/api/reviews/{ctx['job_id']}/asset/set-blank",
            json={"clip_index": 0},
        )
        assert resp.status_code == 200
