from __future__ import annotations

from pathlib import Path

from packages.runtime_adapters.base import BaseRuntimeAdapter


def run_fake_phase_bundle(adapter: BaseRuntimeAdapter, attempt_root: Path) -> list[Path]:
    return adapter.build_fake_outputs(attempt_root)
