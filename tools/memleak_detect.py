#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "psutil",
# ]
# ///
"""Run pytest in batches and sample RSS to detect memory leaks."""

import os
import subprocess
import sys
import time

import psutil


def sample_rss(label: str) -> int:
    proc = psutil.Process()
    rss = proc.memory_info().rss // 1024
    print(f"[{label}] RSS={rss}KB")
    return rss


def run_test_suite(label: str, pytest_args: list[str]) -> int:
    """Run pytest and return peak RSS after collection."""
    sample_rss(f"{label}_before")
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "ignore"
    result = subprocess.run(
        [sys.executable, "-m", "pytest"] + pytest_args,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    print(result.stdout.splitlines()[-5:])
    if result.stderr.strip():
        print("stderr:", result.stderr.splitlines()[-3:])
    rss = sample_rss(f"{label}_after")
    return rss


def main():
    print("=== Memory leak feedback loop ===")
    baselines = []

    # 1. Collect known heavy files
    heavy_dirs = [
        "tests/control_plane/",
    ]

    for i in range(3):
        print(f"\n--- Iteration {i + 1} ---")
        rss = run_test_suite(f"iter{i}", heavy_dirs + ["-q", "--tb=line"])
        baselines.append(rss)
        time.sleep(1)

    # Report trend
    print(f"\n=== Trend: {baselines[0]} -> {baselines[-1]} KB ===")
    if baselines[-1] > baselines[0] * 1.5:
        print("WARNING: RSS grew >50% across 3 runs — likely leak")
    else:
        print("OK: RSS stable")

    return 0 if baselines[-1] <= baselines[0] * 2 else 1


if __name__ == "__main__":
    sys.exit(main())
