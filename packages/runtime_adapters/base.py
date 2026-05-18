from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseRuntimeAdapter(ABC):
    profile_name: str

    @abstractmethod
    def ensure_tools(self) -> None:
        """Verify the local runtime is ready."""

    @abstractmethod
    def attempt_root(self, workspace_root: Path, attempt_id: str) -> Path:
        """Create or return the workspace for one attempt."""

    @abstractmethod
    def build_fake_outputs(self, attempt_root: Path) -> list[Path]:
        """Produce the minimal fake outputs for Task 5."""
