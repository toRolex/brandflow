"""Final review phase handler (pure gate)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


def run(_orchestrator: PhaseOrchestrator, _ctx: PhaseContext) -> list:
    """final_review: pure gate — no handler logic.  Burn happens in final_rendering."""
    return []
