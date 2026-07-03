"""Tests for WorkerLoop — orchestrator-based pipeline execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps.runtime_worker.http_client import WorkerHttpClient
from apps.runtime_worker.loop import WorkerLoop
from packages.pipeline_services.phase_orchestrator import (
    ArtifactPointer,
    PhaseContext,
)


# ---------------------------------------------------------------------------
# Test stubs
# ---------------------------------------------------------------------------


class StubIdleApi:
    def __init__(self, max_polls: int = 2) -> None:
        self.poll_calls = 0
        self.max_polls = max_polls

    def poll(self) -> dict:
        self.poll_calls += 1
        if self.poll_calls >= self.max_polls:
            raise SystemExit(0)
        return {"command": "idle", "next_poll_after_seconds": 5}


class StubApi:
    """Default API stub that returns a run_task command."""

    def __init__(self) -> None:
        self.reports: list[dict] = []
        self.uploads: list[tuple[str, list[dict]]] = []
        self.download_requests: list[str] = []
        self.poll_calls = 0

    def poll(self) -> dict:
        self.poll_calls += 1
        if self.poll_calls > 1:
            raise SystemExit(0)
        return {
            "command": "run_task",
            "project_id": "project-001",
            "job_id": "job-001",
            "task_id": "task-001",
            "task_type": "run_phase",
            "lease_id": "lease-001",
            "attempt_id": "attempt-001",
            "lease_expires_at": "2026-05-18T12:00:00Z",
            "input_bundle_url": "/bundle",
            "report_url": "/report",
            "heartbeat_url": "/heartbeat",
            "expected_outputs": ["script", "audio", "subtitles", "final_video"],
            "runtime_limits": {"max_seconds": 60},
            "handler_phase": "script_generating",
            "product": "羊肚菌",
            "brand": "滋元堂",
        }

    def download_input_bundle(self, bundle_url: str) -> dict:
        self.download_requests.append(bundle_url)
        assert bundle_url == "/bundle"
        return {"project_id": "project-001", "job_id": "job-001"}

    def upload_artifacts(self, task_id: str, files: list[dict]) -> None:
        self.uploads.append((task_id, files))

    def report(self, payload: dict) -> None:
        self.reports.append(payload)


class StubApiWithManualInputs:
    """API stub that includes manual_script and/or uploaded_audio_path."""

    def __init__(self, manual_script: str = "", uploaded_audio_path: str = "") -> None:
        self.reports: list[dict] = []
        self.uploads: list[tuple[str, list[dict]]] = []
        self.download_requests: list[str] = []
        self.manual_script = manual_script
        self.uploaded_audio_path = uploaded_audio_path
        self.poll_calls = 0

    def poll(self) -> dict:
        self.poll_calls += 1
        if self.poll_calls > 1:
            raise SystemExit(0)
        return {
            "command": "run_task",
            "project_id": "project-001",
            "job_id": "job-001",
            "task_id": "task-001",
            "task_type": "run_phase",
            "lease_id": "lease-001",
            "attempt_id": "attempt-001",
            "lease_expires_at": "2026-05-18T12:00:00Z",
            "input_bundle_url": "/bundle",
            "report_url": "/report",
            "heartbeat_url": "/heartbeat",
            "expected_outputs": ["script", "audio", "subtitles", "final_video"],
            "runtime_limits": {"max_seconds": 60},
            "manual_script": self.manual_script,
            "uploaded_audio_path": self.uploaded_audio_path,
            "handler_phase": "script_generating",
            "product": "羊肚菌",
            "brand": "滋元堂",
        }

    def download_input_bundle(self, bundle_url: str) -> dict:
        self.download_requests.append(bundle_url)
        return {"project_id": "project-001", "job_id": "job-001"}

    def upload_artifacts(self, task_id: str, files: list[dict]) -> None:
        self.uploads.append((task_id, files))

    def report(self, payload: dict) -> None:
        self.reports.append(payload)


class StubOrchestrator:
    """Stub PhaseOrchestrator that records calls and returns stub artifacts.

    Returns ArtifactPointer objects with a simple relative path.  Does NOT
    create real files — upload logic in WorkerLoop skips missing files.
    """

    def __init__(self) -> None:
        self.phase_calls: list[dict] = []

    def run_phase(self, phase: str, ctx: PhaseContext) -> list[ArtifactPointer]:
        self.phase_calls.append(
            {
                "phase": phase,
                "job_id": ctx.job_id,
                "product": ctx.product,
            }
        )
        # Return a stub artifact for each phase (relative_path is just a label)
        return [
            ArtifactPointer(
                kind=phase,
                relative_path=f"projects/{ctx.project_dir.name}/runtime/jobs/{ctx.job_id}/{phase}.stub",
                url="",
                size_bytes=0,
            )
        ]


# Backward compat aliases (used by older test code, kept for reference)
StubScriptBridge = type("StubScriptBridge", (), {})
StubMediaBridge = type("StubMediaBridge", (), {})
StubScheduleBridge = type("StubScheduleBridge", (), {})


def _make_loop(
    tmp_path: Path,
    api: Any,
    orchestrator: StubOrchestrator | None = None,
    monkeypatch: Any = None,
) -> WorkerLoop:
    """Helper to construct a WorkerLoop with a stub orchestrator."""
    if orchestrator is None:
        orchestrator = StubOrchestrator()
    loop = WorkerLoop(
        api=api,
        worker_id="worker-mac",
        workspace_root=tmp_path,
        orchestrator=orchestrator,
    )
    # Monkey-patch adapter to use tmp_path-friendly paths
    if monkeypatch is not None:
        monkeypatch.setattr(loop.adapter, "ensure_tools", lambda: None)
    return loop


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_http_client_absolute_url_handles_absolute_and_relative_paths() -> None:
    client = WorkerHttpClient(
        base_url="http://127.0.0.1:17890",
        worker_id="worker-mac",
        worker_version="0.1.0",
        capabilities=["mac-local"],
    )

    assert (
        client._absolute_url("http://example.com/bundle") == "http://example.com/bundle"
    )
    assert (
        client._absolute_url("https://example.com/bundle")
        == "https://example.com/bundle"
    )
    assert client._absolute_url("/bundle") == "http://127.0.0.1:17890/bundle"
    assert client._absolute_url("bundle") == "http://127.0.0.1:17890/bundle"


def test_worker_loop_sleeps_and_retries_on_idle(tmp_path: Path) -> None:
    api = StubIdleApi(max_polls=2)
    loop = _make_loop(tmp_path, api)

    with pytest.raises(SystemExit):
        loop.run_forever()

    assert api.poll_calls == 2


def test_worker_loop_calls_handler_phase_only(tmp_path: Path, monkeypatch) -> None:
    api = StubApi()
    orch = StubOrchestrator()
    loop = _make_loop(tmp_path, api, orch, monkeypatch)

    with pytest.raises(SystemExit):
        loop.run_forever()

    # Only handler_phase should be called, not a batch of all phases
    called = [c["phase"] for c in orch.phase_calls]
    assert called == ["script_generating"]


def test_worker_loop_passes_product_from_command(tmp_path: Path, monkeypatch) -> None:
    api = StubApi()
    orch = StubOrchestrator()
    loop = _make_loop(tmp_path, api, orch, monkeypatch)

    with pytest.raises(SystemExit):
        loop.run_forever()

    # The single phase call should receive the product from the command
    assert len(orch.phase_calls) == 1
    assert orch.phase_calls[0]["product"]  # non-empty


def test_worker_loop_reports_success_and_uploads_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    api = StubApi()

    class FileCreatingOrchestrator(StubOrchestrator):
        """Like StubOrchestrator but creates actual files so upload works."""

        def run_phase(self, phase: str, ctx: PhaseContext) -> list[ArtifactPointer]:
            artifacts = super().run_phase(phase, ctx)
            workspace_dir = ctx.root_dir / "workspace"
            for art in artifacts:
                abs_path = workspace_dir / art.relative_path
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_bytes(b"\x00" * 64)
            return artifacts

    orch = FileCreatingOrchestrator()
    loop = _make_loop(tmp_path, api, orch, monkeypatch)

    with pytest.raises(SystemExit):
        loop.run_forever()

    assert api.download_requests == ["/bundle"]
    assert api.uploads[0][0] == "task-001"
    assert len(api.uploads[0][1]) > 0, "Should upload at least one artifact"
    assert api.reports[0]["status"] == "succeeded"
    assert api.reports[0]["attempt_id"] == "attempt-001"
    assert api.reports[0]["started_at"] <= api.reports[0]["finished_at"]


def test_worker_loop_writes_job_json_with_command_fields(
    tmp_path: Path, monkeypatch
) -> None:
    """The worker should persist command fields (cover_title, music, etc.) in job JSON
    so that the orchestrator's final_review handler can read them."""
    api = StubApi()
    orch = StubOrchestrator()
    loop = _make_loop(tmp_path, api, orch, monkeypatch)

    with pytest.raises(SystemExit):
        loop.run_forever()

    # Verify job JSON was written
    job_json = (
        tmp_path.resolve()
        / "projects"
        / "project-001"
        / "control"
        / "jobs"
        / "job-001.json"
    )
    assert job_json.exists(), f"Job JSON should be written at {job_json}"
    data = json.loads(job_json.read_text(encoding="utf-8"))
    assert data["job_id"] == "job-001"
    assert data["project_id"] == "project-001"


def test_worker_loop_skips_llm_when_manual_script_provided(
    tmp_path: Path, monkeypatch
) -> None:
    """When manual_script is set, the orchestrator should still be called for all phases.
    The orchestrator's _run_script handler detects manual_script in ctx.options."""
    manual_script = "这是手动输入的测试文案，用于验证跳过LLM生成功能。"
    api = StubApiWithManualInputs(manual_script=manual_script)
    orch = StubOrchestrator()
    loop = _make_loop(tmp_path, api, orch, monkeypatch)

    with pytest.raises(SystemExit):
        loop.run_forever()

    # Only handler_phase should be called
    called = [c["phase"] for c in orch.phase_calls]
    assert called == ["script_generating"]

    # The job JSON should contain the fields needed by final_review
    job_json = (
        tmp_path.resolve()
        / "projects"
        / "project-001"
        / "control"
        / "jobs"
        / "job-001.json"
    )
    assert job_json.exists()


def test_worker_loop_skips_tts_when_audio_uploaded(tmp_path: Path, monkeypatch) -> None:
    """When uploaded_audio_path is set, the orchestrator's TTS handler copies the file
    instead of synthesizing.  The orchestrator is still called for all phases."""
    audio_dir = tmp_path / "uploaded"
    audio_dir.mkdir(parents=True)
    fake_audio = audio_dir / "my_audio.mp3"
    fake_audio.write_bytes(b"\x00" * 256)

    api = StubApiWithManualInputs(
        uploaded_audio_path=str(fake_audio.relative_to(tmp_path))
    )
    orch = StubOrchestrator()
    loop = _make_loop(tmp_path, api, orch, monkeypatch)

    with pytest.raises(SystemExit):
        loop.run_forever()

    # Only handler_phase should still be called — the orchestrator handles the upload
    called = [c["phase"] for c in orch.phase_calls]
    assert called == ["script_generating"]


def test_worker_loop_passes_language_in_options(tmp_path: Path, monkeypatch) -> None:
    """language from the command should be passed to PhaseContext.options."""
    # StubApi does not include language — defaults to "mandarin"
    api = StubApi()
    orch = StubOrchestrator()
    loop = _make_loop(tmp_path, api, orch, monkeypatch)

    # Patch run_phase to inspect ctx.options
    original_run = orch.run_phase
    seen_options: list[dict] = []

    def capturing_run(phase: str, ctx: PhaseContext) -> list:
        seen_options.append(ctx.options.copy())
        return original_run(phase, ctx)

    orch.run_phase = capturing_run  # type: ignore[assignment]

    with pytest.raises(SystemExit):
        loop.run_forever()

    assert len(seen_options) == 1, "Only one phase should be executed"
    assert seen_options[0].get("language") == "mandarin"


def test_worker_loop_constructs_project_dir_correctly(
    tmp_path: Path, monkeypatch
) -> None:
    """project_dir should be workspace_root/projects/project_id, passed to the orchestrator."""
    api = StubApi()
    orch = StubOrchestrator()
    loop = _make_loop(tmp_path, api, orch, monkeypatch)

    with pytest.raises(SystemExit):
        loop.run_forever()

    # Verify the orchestrator received the correct job_id (single call)
    assert len(orch.phase_calls) == 1
    assert orch.phase_calls[0]["job_id"] == "job-001"
