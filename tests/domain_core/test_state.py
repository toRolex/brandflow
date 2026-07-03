from packages.domain_core.models import JobRecord, WorkerLease
from packages.domain_core.state import next_phase, rewind_from_phase
from packages.domain_core.worker_protocol import PollCommandRunTask


def test_phase_progression_reaches_review_gate() -> None:
    assert next_phase("queued") == "script_generating"
    assert next_phase("script_generating") == "script_review"
    assert next_phase("final_review") == "completed"


def test_rewind_from_phase_discards_downstream_phases() -> None:
    phases = rewind_from_phase("asset_retrieving")
    assert phases == [
        "asset_retrieving",
        "asset_review",
        "video_rendering",
        "final_rendering",
        "final_review",
    ]


def test_job_record_defaults_skip_subtitle_and_auto_approve_to_false() -> None:
    record = JobRecord(job_id="job-1", phase="queued", review_status="none")

    assert record.skip_subtitle is False
    assert record.auto_approve is False


def test_job_record_preserves_explicit_skip_subtitle_and_auto_approve() -> None:
    record = JobRecord(
        job_id="job-1",
        phase="queued",
        review_status="none",
        skip_subtitle=True,
        auto_approve=True,
    )

    assert record.skip_subtitle is True
    assert record.auto_approve is True


def test_job_record_serializes_review_state() -> None:
    record = JobRecord(job_id="job-1", phase="queued", review_status="none")
    assert record.model_dump()["phase"] == "queued"


def test_worker_run_task_command_contains_lease_and_attempt() -> None:
    command = PollCommandRunTask(
        command="run_task",
        handler_phase="script_generating",
        project_id="p1",
        job_id="j1",
        task_id="t1",
        task_type="run_phase",
        lease_id="lease-1",
        attempt_id="attempt-1",
        lease_expires_at="2026-05-18T12:00:00Z",
        input_bundle_url="http://localhost/input",
        report_url="http://localhost/report",
        heartbeat_url="http://localhost/heartbeat",
        expected_outputs=["script", "audio"],
        runtime_limits={"max_seconds": 600},
    )
    assert command.attempt_id == "attempt-1"


def test_worker_lease_tracks_current_phase() -> None:
    lease = WorkerLease(
        worker_id="worker-a",
        lease_id="lease-1",
        attempt_id="attempt-1",
        task_id="task-1",
        current_phase="tts_generating",
    )
    assert lease.current_phase == "tts_generating"
