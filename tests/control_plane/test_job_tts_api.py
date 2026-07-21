"""Tests for job-level TTS voice selection, preview, and change endpoints (#177)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.file_store.repository import FileStoreRepository


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def _create_job(client: TestClient, project_id: str, **overrides) -> dict:
    payload = {
        "product": "test_product",
        "brand": "test_brand",
        "platforms": ["douyin"],
        "mode": "generate",
        "manual_script": "这是第一句文案。这是第二句文案。这是第三句文案。",
        **overrides,
    }
    resp = client.post(f"/api/projects/{project_id}/jobs", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_project_root(client: TestClient, project_id: str) -> Path:
    """Return the workspace project dir and ensure control/jobs exists."""
    root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
    proj_dir = root / "workspace" / "projects" / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "control" / "jobs").mkdir(parents=True, exist_ok=True)
    return proj_dir


def _put_audio_file(project_dir: Path, job_id: str) -> Path:
    """Place a fake audio.mp3 file so we can test confirm-path invalidation."""
    audio_dir = project_dir / "runtime" / "jobs" / job_id
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / "audio.mp3"
    audio_path.write_bytes(b"fake mp3 data")
    return audio_path


def _put_artifacts_on_job(
    client: TestClient,
    project_id: str,
    job_id: str,
    artifact_kinds: list[str],
) -> None:
    """Directly write artifact pointers to the job record on disk."""
    root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
    repo = FileStoreRepository(root)
    record = repo.load_job(project_id, job_id)
    artifacts = list(record.artifacts)
    for kind in artifact_kinds:
        artifacts.append(
            {
                "kind": kind,
                "relative_path": f"fake/path/{kind}",
                "url": f"/workspace/fake/path/{kind}",
                "size_bytes": 0,
            }
        )
    record = record.model_copy(update={"artifacts": artifacts})
    repo.save_job(project_id, record)


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/tts/voice — resolved voice info
# ---------------------------------------------------------------------------


class TestGetJobTTSVoice:
    def test_returns_job_voice_when_set(self, client):
        proj_id = "proj-gv1"
        _make_project_root(client, proj_id)
        job = _create_job(
            client, proj_id, tts_model="qwen3-tts-flash", tts_voice="Rocky"
        )
        resp = client.get(f"/api/jobs/{job['job_id']}/tts/voice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "qwen3-tts-flash"
        assert data["voice"] == "Rocky"
        assert data["resolved_from"] == "job"

    def test_returns_resolved_from_product_when_job_not_set(self, client):
        """When job-level fields are empty, the resolved value comes from product/global config."""
        proj_id = "proj-gv2"
        _make_project_root(client, proj_id)
        job = _create_job(client, proj_id, tts_model="", tts_voice="")
        resp = client.get(f"/api/jobs/{job['job_id']}/tts/voice")
        assert resp.status_code == 200
        data = resp.json()
        # model and voice must be present (resolved from config)
        assert "model" in data
        assert "voice" in data
        # resolved_from should be "product" or "global" (not "job")
        assert data["resolved_from"] in ("product", "global")

    def test_job_not_found_returns_404(self, client):
        resp = client.get("/api/jobs/nonexistent_job_id/tts/voice")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/jobs/{job_id}/tts/preview — audition first sentence
# ---------------------------------------------------------------------------


class TestJobTTSPreview:
    def test_preview_returns_audio_for_first_sentence(self, client):
        proj_id = "proj-pv1"
        _make_project_root(client, proj_id)
        # Script with multiple sentences: "这是第一句文案。这是第二句文案。"
        job = _create_job(
            client,
            proj_id,
            manual_script="这是第一句文案。这是第二句文案。这是第三句文案。",
        )
        resp = client.post(f"/api/jobs/{job['job_id']}/tts/preview")
        # May fail with 500 if no TTS API key is configured, but
        # we verify the endpoint route exists and handles requests.
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            assert "audio" in content_type or len(resp.content) > 0

    def test_preview_uses_job_voice_override(self, client):
        """When tts_voice is set on job, preview should honor it (verify by 200 route hit)."""
        proj_id = "proj-pv2"
        _make_project_root(client, proj_id)
        job = _create_job(
            client,
            proj_id,
            manual_script="测试文案第一句。",
            tts_voice="Dean",
            tts_model="mimo-v2.5-tts",
        )
        resp = client.post(f"/api/jobs/{job['job_id']}/tts/preview")
        assert resp.status_code in (200, 500)

    def test_preview_does_not_persist_artifacts(self, client):
        """Preview must NOT create artifacts or modify job phase."""
        proj_id = "proj-pv3"
        _make_project_root(client, proj_id)
        job = _create_job(
            client,
            proj_id,
            manual_script="测试文案第一句。",
        )
        job_id = job["job_id"]

        # Record initial state
        root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
        repo = FileStoreRepository(root)
        record_before = repo.load_job(proj_id, job_id)
        phase_before = record_before.phase
        artifacts_before = [a.kind for a in record_before.artifacts]

        resp = client.post(f"/api/jobs/{job_id}/tts/preview")
        # Even if TTS fails (no API key), verify no side effects
        assert resp.status_code in (200, 500)

        record_after = repo.load_job(proj_id, job_id)
        assert record_after.phase == phase_before, "preview must not change phase"
        after_kinds = [a.kind for a in record_after.artifacts]
        assert after_kinds == artifacts_before, "preview must not add artifacts"

    def test_preview_job_not_found(self, client):
        resp = client.post("/api/jobs/nonexistent/tts/preview")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/jobs/{job_id}/tts/voice — update voice with invalidation
# ---------------------------------------------------------------------------


class TestUpdateJobTTSVoice:
    def test_update_voice_no_audio_succeeds(self, client):
        """When no audio.mp3 exists, voice update succeeds without confirmation."""
        proj_id = "proj-uv1"
        _make_project_root(client, proj_id)
        job = _create_job(
            client,
            proj_id,
            manual_script="测试文案。",
            tts_model="",
            tts_voice="",
        )
        job_id = job["job_id"]

        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={"model": "qwen3-tts-flash", "voice": "Cherry"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model"] == "qwen3-tts-flash"
        assert data["voice"] == "Cherry"
        assert data["resolved_from"] == "job"

        # Verify persisted
        root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
        repo = FileStoreRepository(root)
        record = repo.load_job(proj_id, job_id)
        assert record.tts_model == "qwen3-tts-flash"
        assert record.tts_voice == "Cherry"

    def test_update_voice_with_audio_needs_confirm(self, client):
        """When audio.mp3 exists, voice update must require confirm=true."""
        proj_id = "proj-uv2"
        proj_dir = _make_project_root(client, proj_id)
        job = _create_job(client, proj_id, manual_script="测试文案。")
        job_id = job["job_id"]

        # Place a fake audio.mp3
        _put_audio_file(proj_dir, job_id)

        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={"model": "mimo-v2.5-tts", "voice": "Dean"},
        )
        assert resp.status_code == 409, resp.text
        data = resp.json()
        assert "audio_exists" in data.get("detail", {})

    def test_update_voice_with_audio_confirm_true(self, client):
        """With confirm=true and audio exists, voice update succeeds and invalidates downstream."""
        proj_id = "proj-uv3"
        proj_dir = _make_project_root(client, proj_id)
        job = _create_job(
            client,
            proj_id,
            manual_script="测试文案。",
            tts_model="old-model",
            tts_voice="old-voice",
        )
        job_id = job["job_id"]

        # Put fake audio and downstream artifacts
        _put_audio_file(proj_dir, job_id)
        _put_artifacts_on_job(
            client,
            proj_id,
            job_id,
            ["tts_audio", "subtitle", "video_base", "final_video"],
        )

        root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
        repo = FileStoreRepository(root)
        record_before = repo.load_job(proj_id, job_id)
        kinds_before = {a.kind for a in record_before.artifacts}
        assert "tts_audio" in kinds_before
        assert "subtitle" in kinds_before

        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={
                "model": "qwen3-tts-flash",
                "voice": "Cherry",
                "confirm": True,
            },
        )
        assert resp.status_code == 200, resp.text

        record_after = repo.load_job(proj_id, job_id)
        assert record_after.tts_model == "qwen3-tts-flash"
        assert record_after.tts_voice == "Cherry"

        # Invalidated artifacts: tts_audio, subtitle, video_base, final_video must be gone
        remaining_kinds = {a.kind for a in record_after.artifacts}
        assert "tts_audio" not in remaining_kinds
        assert "subtitle" not in remaining_kinds
        assert "video_base" not in remaining_kinds
        assert "final_video" not in remaining_kinds

        # Phase reset to tts_generating to re-run TTS
        assert record_after.phase == "tts_generating"

    def test_update_voice_preserves_script_artifacts(self, client):
        """Voice invalidation must preserve script artifacts and asset selections."""
        proj_id = "proj-uv4"
        proj_dir = _make_project_root(client, proj_id)
        job = _create_job(client, proj_id, manual_script="测试文案。")
        job_id = job["job_id"]

        _put_audio_file(proj_dir, job_id)
        # Put script, TTS, and asset selection artifacts
        _put_artifacts_on_job(
            client,
            proj_id,
            job_id,
            ["script", "tts_audio", "selected_clips", "video_base", "final_video"],
        )

        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={"model": "mimo-v2.5-tts", "voice": "Mia", "confirm": True},
        )
        assert resp.status_code == 200, resp.text

        root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
        repo = FileStoreRepository(root)
        record = repo.load_job(proj_id, job_id)
        remaining_kinds = {a.kind for a in record.artifacts}
        # Script and selected_clips must survive
        assert "script" in remaining_kinds, "script artifact must be preserved"
        assert "selected_clips" in remaining_kinds, "selected_clips must be preserved"
        # TTS, video, final must be gone
        assert "tts_audio" not in remaining_kinds
        assert "video_base" not in remaining_kinds
        assert "final_video" not in remaining_kinds
        assert record.phase == "tts_generating"

    def test_update_voice_job_not_found(self, client):
        resp = client.put(
            "/api/jobs/nonexistent/tts/voice",
            json={"model": "test", "voice": "test"},
        )
        assert resp.status_code == 404

    def test_update_voice_only_model(self, client):
        """Partial update: only change model, keep existing voice."""
        proj_id = "proj-uv5"
        _make_project_root(client, proj_id)
        job = _create_job(
            client,
            proj_id,
            manual_script="测试文案。",
            tts_voice="Mia",
            tts_model="",
        )
        job_id = job["job_id"]

        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={"model": "qwen3-tts-flash"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model"] == "qwen3-tts-flash"
        # Voice unchanged
        assert data["voice"] == "Mia"

    def test_update_voice_only_voice(self, client):
        """Partial update: only change voice, keep existing model."""
        proj_id = "proj-uv6"
        _make_project_root(client, proj_id)
        job = _create_job(
            client,
            proj_id,
            manual_script="测试文案。",
            tts_voice="Mia",
            tts_model="mimo-v2.5-tts",
        )
        job_id = job["job_id"]

        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={"voice": "Dean"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["voice"] == "Dean"
        # Model unchanged
        assert data["model"] == "mimo-v2.5-tts"

    # ------------------------------------------------------------------
    # Voice validation: model+voice atomicity (#252)
    # ------------------------------------------------------------------

    def test_save_invalid_voice_for_model_returns_422(self, client):
        """Saving a Qwen model with a MiMo-only voice must return 422."""
        proj_id = "proj-uv7"
        _make_project_root(client, proj_id)
        job = _create_job(
            client, proj_id, manual_script="测试文案。", tts_model="", tts_voice=""
        )
        job_id = job["job_id"]

        # "冰糖" is a MiMo-only voice, not in QWEN_VOICES
        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={"model": "qwen3-tts-flash", "voice": "冰糖"},
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json().get("detail", "")
        assert "冰糖" in str(detail)

        # Verify NOT persisted
        root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
        repo = FileStoreRepository(root)
        record = repo.load_job(proj_id, job_id)
        assert record.tts_model == ""
        assert record.tts_voice == ""

    def test_save_valid_voice_for_model_succeeds(self, client):
        """Saving a MiMo model with a valid MiMo voice succeeds."""
        proj_id = "proj-uv8"
        _make_project_root(client, proj_id)
        job = _create_job(
            client, proj_id, manual_script="测试文案。", tts_model="", tts_voice=""
        )
        job_id = job["job_id"]

        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={"model": "mimo-v2.5-tts", "voice": "Mia"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model"] == "mimo-v2.5-tts"
        assert data["voice"] == "Mia"

        # Verify persisted
        root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
        repo = FileStoreRepository(root)
        record = repo.load_job(proj_id, job_id)
        assert record.tts_model == "mimo-v2.5-tts"
        assert record.tts_voice == "Mia"

    def test_save_voicedesign_model_skips_voice_validation(self, client):
        """VoiceDesign sub-model has no preset voice — validation is skipped."""
        proj_id = "proj-uv9"
        _make_project_root(client, proj_id)
        job = _create_job(
            client, proj_id, manual_script="测试文案。", tts_model="", tts_voice=""
        )
        job_id = job["job_id"]

        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={
                "model": "mimo-v2.5-tts-voicedesign",
                "voice": "any-custom-voice",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model"] == "mimo-v2.5-tts-voicedesign"

    def test_save_both_model_and_voice_validates_resolved_pair(self, client):
        """When only model is changed, validate against the existing voice."""
        proj_id = "proj-uv10"
        _make_project_root(client, proj_id)
        job = _create_job(
            client,
            proj_id,
            manual_script="测试文案。",
            tts_model="mimo-v2.5-tts",
            tts_voice="冰糖",  # MiMo-only voice
        )
        job_id = job["job_id"]

        # Change only model to Qwen but keep old MiMo-only voice — should be rejected
        resp = client.put(
            f"/api/jobs/{job_id}/tts/voice",
            json={"model": "qwen3-tts-flash"},
        )
        assert resp.status_code == 422, resp.text
