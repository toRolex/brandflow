"""Tests for ExportTaskService — durable background export task (#180).

Covers the domain seam: task state machine, fingerprint-keyed cache reuse,
stale marking on rerender, restart recovery, and atomic ZIP publication.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from packages.pipeline_services.export_task import ExportTaskService


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    d = tmp_path / "workspace" / "projects" / "proj-001"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def job_dir(project_dir: Path) -> Path:
    d = project_dir / "runtime" / "jobs" / "job-001"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def export_dir(project_dir: Path) -> Path:
    return project_dir / "runtime" / "exports"


def _populate_job(job_dir: Path, workspace_dir: Path) -> None:
    (job_dir / "final.mp4").write_text("final video data")
    (job_dir / "audio.mp3").write_text("audio data")


def _make_service(
    project_dir: Path, job_dir: Path, export_dir: Path, workspace_dir: Path
) -> ExportTaskService:
    return ExportTaskService(
        job_id=job_dir.name,
        job_dir=job_dir,
        workspace_dir=workspace_dir,
        project_dir=project_dir,
        export_dir=export_dir,
        get_scene_config=lambda: {"folders": [], "transition_duration_ms": 500},
    )


@pytest.fixture()
def service(
    project_dir: Path, job_dir: Path, export_dir: Path, tmp_path: Path
) -> ExportTaskService:
    workspace_dir = tmp_path / "workspace"
    _populate_job(job_dir, workspace_dir)
    return _make_service(project_dir, job_dir, export_dir, workspace_dir)


class TestCreateOrReuse:
    def test_create_returns_task_id_not_blocking(
        self, service: ExportTaskService
    ) -> None:
        """Creating an export returns a queued task with an id immediately."""
        task = service.create_or_reuse(fingerprint="fp-a")
        assert task["task_id"]
        assert task["status"] == "queued"
        assert task["fingerprint"] == "fp-a"

    def test_reuse_ready_task_when_fingerprint_unchanged(
        self, service: ExportTaskService
    ) -> None:
        """A ready task is reused when the Final Timeline fingerprint matches."""
        task = service.create_or_reuse(fingerprint="fp-a")
        service.run(task["task_id"])
        assert service.get(task["task_id"])["status"] == "ready"

        again = service.create_or_reuse(fingerprint="fp-a")
        assert again["task_id"] == task["task_id"]
        assert again["status"] == "ready"

    def test_new_task_when_fingerprint_changed(
        self, service: ExportTaskService
    ) -> None:
        """A changed fingerprint produces a fresh queued task (old goes stale)."""
        task = service.create_or_reuse(fingerprint="fp-a")
        service.run(task["task_id"])

        new_task = service.create_or_reuse(fingerprint="fp-b")
        assert new_task["task_id"] != task["task_id"]
        assert new_task["status"] == "queued"


class TestRunAndAtomicPublish:
    def test_run_produces_ready_task_with_valid_zip(
        self, service: ExportTaskService
    ) -> None:
        task = service.create_or_reuse(fingerprint="fp-a")
        service.run(task["task_id"])

        done = service.get(task["task_id"])
        assert done["status"] == "ready"
        zip_path = Path(done["zip_path"])
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert zf.testzip() is None
            assert any("timeline.json" in n for n in zf.namelist())

    def test_no_partial_zip_left_on_failure(
        self, service: ExportTaskService, export_dir: Path
    ) -> None:
        """A build failure leaves no downloadable partial ZIP."""

        def boom(**kwargs):
            raise RuntimeError("encode failed")

        task = service.create_or_reuse(fingerprint="fp-a")
        service.run(task["task_id"], build_fn=boom)

        assert service.get(task["task_id"])["status"] == "failed"
        assert list(export_dir.glob("*.zip")) == []

    def test_progress_reported_during_run(self, service: ExportTaskService) -> None:
        task = service.create_or_reuse(fingerprint="fp-a")
        assert service.get(task["task_id"])["progress"] == 0
        service.run(task["task_id"])
        assert service.get(task["task_id"])["progress"] == 100


class TestMarkStale:
    def test_rerender_makes_ready_task_stale_and_removes_zip(
        self, service: ExportTaskService
    ) -> None:
        task = service.create_or_reuse(fingerprint="fp-a")
        service.run(task["task_id"])
        zip_path = Path(service.get(task["task_id"])["zip_path"])
        assert zip_path.exists()

        service.mark_stale()
        assert service.get(task["task_id"])["status"] == "stale"
        assert not zip_path.exists()

    def test_rerender_makes_running_task_stale(
        self, service: ExportTaskService
    ) -> None:
        task = service.create_or_reuse(fingerprint="fp-a")
        service._set_status(task["task_id"], "running")  # simulate in-flight

        service.mark_stale()
        assert service.get(task["task_id"])["status"] == "stale"

    def test_stale_task_not_reusable(self, service: ExportTaskService) -> None:
        task = service.create_or_reuse(fingerprint="fp-a")
        service.run(task["task_id"])
        service.mark_stale()

        new_task = service.create_or_reuse(fingerprint="fp-a")
        assert new_task["task_id"] != task["task_id"]
        assert new_task["status"] == "queued"


class TestRecovery:
    def test_interrupted_running_task_requeued_on_restart(
        self, project_dir: Path, job_dir: Path, export_dir: Path, tmp_path: Path
    ) -> None:
        """A task left in `running` (process died) is requeued after restart."""
        workspace_dir = tmp_path / "workspace"
        _populate_job(job_dir, workspace_dir)
        svc = _make_service(project_dir, job_dir, export_dir, workspace_dir)
        task = svc.create_or_reuse(fingerprint="fp-a")
        svc._set_status(task["task_id"], "running")

        # Simulate restart: new service instance over the same directory.
        svc2 = _make_service(project_dir, job_dir, export_dir, workspace_dir)
        recovered = svc2.recover_interrupted()

        assert recovered["status"] == "queued"
        assert recovered["task_id"] == task["task_id"]

    def test_ready_task_survives_restart_and_reuses_zip(
        self, project_dir: Path, job_dir: Path, export_dir: Path, tmp_path: Path
    ) -> None:
        """A ready task with a valid ZIP is reused after restart, not rebuilt."""
        workspace_dir = tmp_path / "workspace"
        _populate_job(job_dir, workspace_dir)
        svc = _make_service(project_dir, job_dir, export_dir, workspace_dir)
        task = svc.create_or_reuse(fingerprint="fp-a")
        svc.run(task["task_id"])
        zip_path = Path(svc.get(task["task_id"])["zip_path"])

        svc2 = _make_service(project_dir, job_dir, export_dir, workspace_dir)
        reused = svc2.create_or_reuse(fingerprint="fp-a")
        assert reused["status"] == "ready"
        assert reused["zip_path"] == str(zip_path)

    def test_corrupt_ready_zip_is_deleted_and_rebuilt(
        self, project_dir: Path, job_dir: Path, export_dir: Path, tmp_path: Path
    ) -> None:
        """A ready task whose ZIP fails validation is rebuilt from scratch."""
        workspace_dir = tmp_path / "workspace"
        _populate_job(job_dir, workspace_dir)
        svc = _make_service(project_dir, job_dir, export_dir, workspace_dir)
        task = svc.create_or_reuse(fingerprint="fp-a")
        svc.run(task["task_id"])
        zip_path = Path(svc.get(task["task_id"])["zip_path"])
        zip_path.write_bytes(b"corrupt not a zip")

        svc2 = _make_service(project_dir, job_dir, export_dir, workspace_dir)
        task_after = svc2.create_or_reuse(fingerprint="fp-a")
        # Corrupt output is not reused as-is; it must be re-queued and rebuilt.
        assert task_after["status"] == "queued"
        svc2.run(task_after["task_id"])
        assert svc2.get(task_after["task_id"])["status"] == "ready"
        with zipfile.ZipFile(svc2.get(task_after["task_id"])["zip_path"], "r") as zf:
            assert zf.testzip() is None
