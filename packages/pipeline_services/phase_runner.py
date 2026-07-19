from __future__ import annotations

from pathlib import Path

from packages.runtime_adapters import RuntimeAdapter


def run_fake_phase_bundle(adapter: RuntimeAdapter, attempt_root: Path) -> list[Path]:
    return adapter.build_fake_outputs(attempt_root)
