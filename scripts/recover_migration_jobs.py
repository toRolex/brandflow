#!/usr/bin/env python3
"""One-time recovery script: migrate stuck ``migration_required`` jobs back to ``queued``.

Scans every project under the configured root directory, finds jobs whose
phase is ``migration_required``, checks whether the corresponding product has
a usable scene-config (``scene.folders``), and if so resets the job to
``queued`` with ``scene_folder_ids`` backfilled to the configured folder
paths.  Jobs without a product-level scene config are skipped with a note.

Safe to run repeatedly (idempotent): already-recovered jobs are no longer in
``migration_required`` and will be skipped on re-runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.domain_core.models import JobRecord
from packages.file_store.repository import FileStoreRepository
from packages.provider_config.config_reader import ConfigReader


def _discover_project_ids(root_dir: Path) -> list[str]:
    projects_root = root_dir / "workspace" / "projects"
    if not projects_root.exists():
        return []
    return sorted(
        p.name
        for p in projects_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def recover_jobs(root_dir: Path) -> tuple[int, int]:
    """Scan and recover migration_required jobs.

    Returns (recovered_count, skipped_count).
    """
    config_reader = ConfigReader(config_dir=str(root_dir / "config"))
    repo = FileStoreRepository(root_dir)

    project_ids = _discover_project_ids(root_dir)
    if not project_ids:
        print("⚠️  未发现项目目录 (workspace/projects/ 为空)")
        return 0, 0

    recovered = 0
    skipped = 0

    for project_id in project_ids:
        jobs = repo.list_jobs(project_id)
        for job_summary in jobs:
            job_id = job_summary.get("job_id", "")
            if not job_id:
                continue

            record = repo.load_job(project_id, job_id)
            if record.phase != "migration_required":
                continue

            product = record.product
            scene_cfg = config_reader.get_scene_config(product_id=product)
            folders = [
                entry.get("path", "")
                for entry in scene_cfg.get("folders", [])
                if entry.get("path")
            ]

            if not folders:
                print(
                    f"⏭  跳过  {project_id}/{job_id}  (product={product!r}, "
                    f"无可用场景配置)"
                )
                skipped += 1
                continue

            record = record.model_copy(
                update={
                    "phase": "queued",
                    "scene_folder_ids": folders,
                    "failed_phase": None,
                }
            )
            repo.save_job(project_id, record)
            print(
                f"✅  恢复  {project_id}/{job_id}  (product={product!r}, "
                f"scene_folder_ids={folders})"
            )
            recovered += 1

    return recovered, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="恢复 stuck 在 migration_required 的 Job"
    )
    parser.add_argument(
        "--root",
        default=".",
        help="仓库根目录 (默认当前目录)",
    )
    args = parser.parse_args()

    root_dir = Path(args.root).resolve()
    print(f"📁  扫描目录: {root_dir}")
    recovered, skipped = recover_jobs(root_dir)
    print(f"\n📊  汇总: 恢复 {recovered}, 跳过 {skipped}")


if __name__ == "__main__":
    main()
