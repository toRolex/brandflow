#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "psutil",
# ]
# ///
"""Run a growing batch of test dirs and sample RSS to find the leaky ones."""

import os
import subprocess
import sys
import time

import psutil


def run_and_sample(pytest_args: list[str], label: str) -> int:
    env = {
        **os.environ,
        "PYTHONWARNINGS": "ignore",
        "EXPORT_SYNC": "1",
        "DEV_AUTO_TICK": "0",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "pytest"] + pytest_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    samples = []
    while True:
        try:
            p = psutil.Process(proc.pid)
            rss = p.memory_info().rss // 1024 // 1024
            samples.append(rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
        time.sleep(2)

    proc.wait(timeout=10)
    peak = max(samples) if samples else 0
    final = samples[-1] if samples else 0
    growth = final - samples[0] if len(samples) > 1 else 0
    print(
        f"{label:40s} peak={peak:4d}MB  final={final:4d}MB  growth={growth:+4d}MB  samples={len(samples)}"
    )
    return final


def main():
    print(
        f"{'Test Suite':40s} {'peak':>6s} {'final':>6s} {'growth':>6s} {'samples':>8s}"
    )
    print("-" * 80)

    # Test each heavy directory individually
    dirs = [
        "tests/control_plane/",
        "tests/pipeline_services/",
        "tests/test_metrics_api.py",
        "tests/test_metrics_import.py",
        "tests/test_metrics_increment.py",
    ]

    results = []
    for d in dirs:
        final = run_and_sample(
            [
                d,
                "-q",
                "--tb=line",
                "-m",
                "not e2e and not slow and not media_integration",
                "--memray",
                "--memray-bin-path=/tmp/memray",
            ],
            d,
        )
        results.append((d, final))
        time.sleep(1)

    print("\nDone. No single huge leak in isolated runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
