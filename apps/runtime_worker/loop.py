"""WorkerLoop — pulls tasks from the control plane and runs a single phase.

Replaces the old inline pipeline (_DefaultMediaBridge + manual phase wiring)
with orchestrated phase execution.  The same PhaseOrchestrator used by
_auto_tick in the control plane is reused here, so worker and control-plane
share identical pipeline logic.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.runtime_worker.http_client import WorkerHttpClient
from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
    PhaseOrchestrator,
)
from packages.runtime_adapters.mac_local import MacLocalRuntimeAdapter


class WorkerLoop:
    """Pulls a task from *api*, runs the single requested phase, uploads artifact."""

    def __init__(
        self,
        api: Any,
        worker_id: str,
        workspace_root: Path,
        orchestrator: PhaseOrchestrator,
    ) -> None:
        self.api = api
        self.worker_id = worker_id
        self.workspace_root = workspace_root
        self.orchestrator = orchestrator

    def run_forever(self) -> None:
        """Poll 任务，根据 handler_phase 执行单个 phase，report 后继续轮询。"""
        while True:
            command = self.api.poll()
            if command["command"] == "idle":
                time.sleep(5)
                continue

            started_at = datetime.now(timezone.utc).isoformat()
            self.adapter.ensure_tools()

            self.api.download_input_bundle(command["input_bundle_url"])

            root_dir = Path.cwd()
            project_dir = (
                root_dir / self.workspace_root / "projects" / command["project_id"]
            ).resolve()
            job_id = command["job_id"]
            handler_phase = command.get("handler_phase", "")

            # Write job JSON so the orchestrator can read cover_title, music, etc.
            job_json_path = project_dir / "control" / "jobs" / f"{job_id}.json"
            job_json_path.parent.mkdir(parents=True, exist_ok=True)
            existing_job: dict[str, Any] = {}
            if job_json_path.exists():
                existing_job = json.loads(job_json_path.read_text(encoding="utf-8"))
            for key, val in [
                ("job_id", job_id),
                ("project_id", command["project_id"]),
                (
                    "product",
                    command.get("product", os.environ.get("PRODUCT", "")),
                ),
                ("brand", command.get("brand", "")),
                ("platform", command.get("platform", "")),
                ("cover_title", command.get("cover_title") or {}),
                ("music_track_path", command.get("music_track_path", "")),
                ("music_volume", command.get("music_volume", 80)),
            ]:
                if key not in existing_job:
                    existing_job[key] = val
            job_json_path.write_text(
                json.dumps(existing_job, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            # Build PhaseContext
            product = command.get("product", os.environ.get("PRODUCT", ""))
            brand = command.get("brand", "")
            ctx = PhaseContext(
                job_id=job_id,
                project_dir=project_dir,
                root_dir=root_dir,
                product=product,
                brand=brand,
                options={
                    "manual_script": command.get("manual_script", ""),
                    "uploaded_audio_path": command.get("uploaded_audio_path", ""),
                    "language": command.get("language", "mandarin"),
                },
            )

            # Execute the single requested phase and any parallel phases
            try:
                artifacts = self.orchestrator.run_phase(handler_phase, ctx)
                parallel_phases: list[str] = command.get("parallel_phases", [])
                for pp in parallel_phases:
                    pp_artifacts = self.orchestrator.run_phase(pp, ctx)
                    artifacts.extend(pp_artifacts)

                # Upload artifacts
                workspace_dir = root_dir / "workspace"
                uploaded_files = []
                for art in artifacts:
                    if not art.relative_path:
                        continue
                    abs_path = workspace_dir / art.relative_path
                    if abs_path.exists():
                        uploaded_files.append(
                            {
                                "relative_path": art.relative_path,
                                "size_bytes": abs_path.stat().st_size,
                            }
                        )
                if uploaded_files:
                    self.api.upload_artifacts(command["task_id"], uploaded_files)

                # Report success
                status = "succeeded"
                logs = "orchestrator completed"
                error = {}
            except Exception as e:
                print(
                    f"[WORKER] Phase {handler_phase} failed: {type(e).__name__}: {e}",
                    flush=True,
                )
                import traceback
                traceback.print_exc()
                status = "failed"
                logs = f"phase execution error: {e}"
                error = {"message": str(e), "type": type(e).__name__}
                uploaded_files = []

            finished_at = datetime.now(timezone.utc).isoformat()
            self.api.report(
                {
                    "worker_id": self.worker_id,
                    "project_id": command["project_id"],
                    "job_id": job_id,
                    "task_id": command["task_id"],
                    "attempt_id": command["attempt_id"],
                    "lease_id": command["lease_id"],
                    "status": status,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "artifact_manifest": {"files": uploaded_files},
                    "metrics": {},
                    "logs_summary": logs,
                    "error": error,
                }
            )

    @property
    def adapter(self) -> MacLocalRuntimeAdapter:
        """Lazy adapter for ensure_tools() (no-op on mac-local)."""
        if not hasattr(self, "_adapter"):
            self._adapter = MacLocalRuntimeAdapter()
        return self._adapter


def _build_orchestrator(root_dir: Path) -> PhaseOrchestrator:
    """Construct a PhaseOrchestrator with real service dependencies."""
    from packages.pipeline_services.phase_orchestrator import create_orchestrator

    return create_orchestrator(root_dir)


def main() -> None:
    worker_id = os.environ.get("WORKER_ID", "worker-mac")
    workspace_root = Path(os.environ.get("WORKSPACE_ROOT", "workspace"))
    root_dir = Path.cwd()
    api = WorkerHttpClient(
        base_url=os.environ.get("CONTROL_PLANE_URL", "http://127.0.0.1:17890"),
        worker_id=worker_id,
        worker_version="0.1.0",
        capabilities=["mac-local"],
    )
    orchestrator = _build_orchestrator(root_dir)
    WorkerLoop(
        api=api,
        worker_id=worker_id,
        workspace_root=workspace_root,
        orchestrator=orchestrator,
    ).run_forever()
