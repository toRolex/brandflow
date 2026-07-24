"""
Batched test runner — 每批 N 个测试文件在独立子进程中运行。

解决单进程跑全量测试时 sys.modules 跨文件累积导致 RSS 暴涨的问题。
每个子进程跑完一批文件后退出，内存自动归还 OS。

用法:
    uv run python scripts/run_tests.py              # 跑全部 (默认每批 5 文件)
    uv run python scripts/run_tests.py pipeline      # 只跑 pipeline_services
    uv run python scripts/run_tests.py -x            # 遇错即停
    uv run python scripts/run_tests.py --batch 3     # 每批 3 文件
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

DEFAULT_BATCH = 5


def collect_all_files() -> list[tuple[str, str]]:
    """返回 (目录名, 文件路径) 的列表。"""
    files: list[tuple[str, str]] = []

    # 根目录 test 文件
    for f in sorted(TESTS.glob("test_*.py")):
        files.append(("root", str(f)))

    # 子目录
    for d in sorted(TESTS.iterdir()):
        if d.is_dir() and not d.name.startswith(("_", ".")):
            for f in sorted(d.glob("test_*.py")):
                files.append((d.name, str(f)))

    return files


def make_batches(
    files: list[tuple[str, str]], batch_size: int
) -> list[tuple[str, list[str]]]:
    """将文件列表按 batch_size 切片，每片一个 batch。"""
    batches: list[tuple[str, list[str]]] = []
    for i in range(0, len(files), batch_size):
        chunk = files[i : i + batch_size]
        # 用第一个文件的目录名命名
        dirs = sorted(set(d for d, _ in chunk))
        name = "/".join(dirs) if len(dirs) <= 2 else f"{dirs[0]}+{len(dirs) - 1}"
        paths = [f for _, f in chunk]
        batches.append((name, paths))
    return batches


def run_batch(
    batch_id: int, total: int, name: str, files: list[str], extra_args: list[str]
) -> tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", *files, "-q", "--tb=short", *extra_args]
    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
    elapsed = time.monotonic() - t0

    # 提取结果行
    summary = ""
    for line in result.stdout.splitlines():
        if any(k in line for k in ("passed", "failed", "error", "no tests ran")):
            summary = line.strip()

    ok = result.returncode in (0, 5)  # 0=all pass, 5=no tests
    status = "✅" if ok else "❌"
    prefix = f"[{batch_id}/{total}]"
    return (
        ok,
        f"{prefix} {status} {name:<35} {summary or 'no output':<55} ({elapsed:.1f}s)",
    )


def main():
    extra_args = list(sys.argv[1:])
    filter_keyword = None
    batch_size = DEFAULT_BATCH

    # 解析自定义参数
    remaining: list[str] = []
    i = 0
    while i < len(extra_args):
        if extra_args[i] == "--batch" and i + 1 < len(extra_args):
            batch_size = int(extra_args[i + 1])
            i += 2
            continue
        if not extra_args[i].startswith("-") and filter_keyword is None:
            filter_keyword = extra_args[i]
            i += 1
            continue
        remaining.append(extra_args[i])
        i += 1

    all_files = collect_all_files()
    if filter_keyword:
        all_files = [
            (d, f) for d, f in all_files if filter_keyword in d or filter_keyword in f
        ]

    batches = make_batches(all_files, batch_size)
    total_files = len(all_files)

    print(
        f"🧪 Running {total_files} test files in {len(batches)} batches (batch_size={batch_size})\n"
    )

    results: list[tuple[bool, str]] = []
    t0 = time.monotonic()
    for idx, (name, files) in enumerate(batches, 1):
        ok, line = run_batch(idx, len(batches), name, files, remaining)
        results.append((ok, line))
        print(line, flush=True)
        if not ok and "-x" in remaining:
            print("\n⛔ Stopping on first failure (-x)")
            break

    total_time = time.monotonic() - t0
    passed = sum(1 for ok, _ in results if ok)
    failed = len(results) - passed

    print(f"\n{'=' * 70}")
    print(
        f"{'✅ ALL PASSED' if failed == 0 else f'❌ {failed} BATCH(ES) FAILED'} — {passed}/{len(results)} batches, {total_time:.1f}s total"
    )

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
