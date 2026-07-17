"""Structured phase execution results and externally visible lifecycle state."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from packages.domain_core.models import (
    ArtifactPointer,
    ExecutionFailure,
    ExecutionStatus,
    PhaseExecutionState,
)


class PhaseExecutionSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["success"] = "success"
    artifacts: list[ArtifactPointer] = Field(default_factory=list)


class PhaseExecutionFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["failure"] = "failure"
    error: ExecutionFailure


PhaseExecutionResult = Annotated[
    PhaseExecutionSuccess | PhaseExecutionFailure,
    Field(discriminator="outcome"),
]

_PHASE_EXECUTION_RESULT_ADAPTER = TypeAdapter(PhaseExecutionResult)


def parse_phase_execution_result(value: object) -> PhaseExecutionResult:
    """Validate an untrusted structured phase result."""

    return _PHASE_EXECUTION_RESULT_ADAPTER.validate_python(value)


def adapt_legacy_artifacts(
    artifacts: list[ArtifactPointer],
) -> PhaseExecutionSuccess:
    """Temporarily adapt an artifact-list handler to the expanded contract.

    This compatibility boundary is intentionally explicit so the later handler
    contract migration (Issue #171) can remove it without changing the result
    models.
    """

    return PhaseExecutionSuccess(artifacts=artifacts)


# Re-export lifecycle types from the result boundary for callers that do not
# need to know how JobRecord stores them.
__all__ = [
    "ExecutionFailure",
    "ExecutionStatus",
    "PhaseExecutionFailure",
    "PhaseExecutionResult",
    "PhaseExecutionState",
    "PhaseExecutionSuccess",
    "adapt_legacy_artifacts",
    "parse_phase_execution_result",
]
