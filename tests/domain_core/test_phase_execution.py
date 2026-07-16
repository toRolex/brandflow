from __future__ import annotations

import pytest
from pydantic import ValidationError

from packages.domain_core.models import ArtifactPointer
from packages.domain_core.phase_execution import (
    ExecutionFailure,
    PhaseExecutionFailure,
    PhaseExecutionState,
    PhaseExecutionSuccess,
    parse_phase_execution_result,
)


def _artifact() -> ArtifactPointer:
    return ArtifactPointer(kind="script", relative_path="jobs/j1/script.json")


def test_success_result_round_trips_with_artifacts() -> None:
    result = parse_phase_execution_result(
        {"outcome": "success", "artifacts": [_artifact().model_dump()]}
    )

    assert isinstance(result, PhaseExecutionSuccess)
    assert result.artifacts == [_artifact()]


def test_failure_result_requires_structured_failure_data() -> None:
    result = parse_phase_execution_result(
        {
            "outcome": "failure",
            "error": {
                "code": "TTS_PROVIDER_UNAVAILABLE",
                "message": "配音服务暂时不可用，请稍后重试。",
                "retryable": True,
            },
        }
    )

    assert isinstance(result, PhaseExecutionFailure)
    assert result.error.code == "TTS_PROVIDER_UNAVAILABLE"
    assert result.error.retryable is True


@pytest.mark.parametrize(
    "error",
    [
        {"message": "try again", "retryable": True},
        {"code": "TRANSIENT", "retryable": True},
        {"code": "TRANSIENT", "message": "try again"},
        {"code": "", "message": "try again", "retryable": True},
        {"code": "TRANSIENT", "message": "", "retryable": True},
    ],
)
def test_failure_result_rejects_missing_or_blank_required_fields(error: dict) -> None:
    with pytest.raises(ValidationError):
        parse_phase_execution_result({"outcome": "failure", "error": error})


@pytest.mark.parametrize(
    "payload",
    [
        {
            "outcome": "success",
            "artifacts": [],
            "error": {
                "code": "IMPOSSIBLE",
                "message": "success cannot contain an error",
                "retryable": False,
            },
        },
        {
            "outcome": "failure",
            "artifacts": [],
            "error": {
                "code": "FAILED",
                "message": "failure cannot contain artifacts",
                "retryable": False,
            },
        },
        {"outcome": "unknown", "artifacts": []},
    ],
)
def test_result_rejects_unknown_or_mixed_variants(payload: dict) -> None:
    with pytest.raises(ValidationError):
        parse_phase_execution_result(payload)


@pytest.mark.parametrize(
    ("status", "current_attempt", "error"),
    [
        ("pending", 0, None),
        ("running", 1, None),
        ("retrying", 2, None),
        (
            "retrying",
            2,
            ExecutionFailure(
                code="TTS_PROVIDER_UNAVAILABLE",
                message="配音服务不可用，正在重试。",
                retryable=True,
            ),
        ),
        (
            "failed",
            3,
            ExecutionFailure(
                code="TTS_PROVIDER_UNAVAILABLE",
                message="配音服务不可用。",
                retryable=True,
            ),
        ),
        ("succeeded", 1, None),
    ],
)
def test_execution_state_accepts_every_lifecycle_status(
    status: str,
    current_attempt: int,
    error: ExecutionFailure | None,
) -> None:
    state = PhaseExecutionState(
        status=status,
        current_attempt=current_attempt,
        max_attempts=3,
        error=error,
    )

    assert state.status == status
    assert state.current_attempt == current_attempt
    assert state.max_attempts == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "unknown", "current_attempt": 0, "max_attempts": 3},
        {"status": "pending", "current_attempt": 4, "max_attempts": 3},
        {"status": "running", "current_attempt": 0, "max_attempts": 3},
        {"status": "retrying", "current_attempt": 3, "max_attempts": 3},
        {
            "status": "retrying",
            "current_attempt": 1,
            "max_attempts": 3,
            "error": {
                "code": "SCRIPT_INVALID",
                "message": "non-retryable error cannot justify a retry",
                "retryable": False,
            },
        },
        {"status": "failed", "current_attempt": 3, "max_attempts": 3},
        {
            "status": "succeeded",
            "current_attempt": 1,
            "max_attempts": 3,
            "error": {
                "code": "SHOULD_NOT_EXIST",
                "message": "invalid",
                "retryable": False,
            },
        },
    ],
)
def test_execution_state_rejects_illegal_combinations(payload: dict) -> None:
    with pytest.raises(ValidationError):
        PhaseExecutionState.model_validate(payload)
