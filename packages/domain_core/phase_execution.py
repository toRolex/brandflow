"""Structured phase execution results and externally visible lifecycle state."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, TypeAdapter

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
    _cause: Exception | None = PrivateAttr(default=None)

    @property
    def cause(self) -> Exception | None:
        """Return the in-process exception without exposing it on the wire."""
        return self._cause

    @classmethod
    def from_exception(
        cls,
        *,
        error: ExecutionFailure,
        cause: Exception,
    ) -> "PhaseExecutionFailure":
        """Build a serializable failure that retains local traceback context."""
        result = cls(error=error)
        result._cause = cause
        return result

    def with_cause(self, cause: Exception) -> "PhaseExecutionFailure":
        """Attach local traceback context to an already classified failure."""
        self._cause = cause
        return self


PhaseExecutionResult = Annotated[
    PhaseExecutionSuccess | PhaseExecutionFailure,
    Field(discriminator="outcome"),
]

_PHASE_EXECUTION_RESULT_ADAPTER = TypeAdapter(PhaseExecutionResult)


def parse_phase_execution_result(value: object) -> PhaseExecutionResult:
    """Validate an untrusted structured phase result."""

    return _PHASE_EXECUTION_RESULT_ADAPTER.validate_python(value)


# Re-export lifecycle types from the result boundary for callers that do not
# need to know how JobRecord stores them.
__all__ = [
    "ExecutionFailure",
    "ExecutionStatus",
    "PhaseExecutionFailure",
    "PhaseExecutionResult",
    "PhaseExecutionState",
    "PhaseExecutionSuccess",
    "parse_phase_execution_result",
]
