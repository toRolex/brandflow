from packages.domain_core.models import JobRecord
from packages.domain_core.models import next_phase, rewind_from_phase


def test_phase_progression_reaches_review_gate() -> None:
    assert next_phase("queued") == "script_generating"
    assert next_phase("script_generating") == "script_review"
    assert next_phase("final_review") == "completed"


def test_rewind_from_phase_discards_downstream_phases() -> None:
    phases = rewind_from_phase("asset_retrieving")
    assert phases == [
        "asset_retrieving",
        "asset_review",
        "montage_assembling",
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


def test_job_record_ignores_legacy_active_attempt_id() -> None:
    record = JobRecord.model_validate(
        {
            "job_id": "j1",
            "phase": "queued",
            "review_status": "none",
            "active_attempt_id": "",
        }
    )

    assert record.job_id == "j1"


def test_job_record_accepts_migration_required_phase() -> None:
    """migration_required is deprecated but kept for backward compat with existing records."""
    record = JobRecord(
        job_id="job-1",
        phase="migration_required",
        review_status="none",
    )
    assert record.phase == "migration_required"
