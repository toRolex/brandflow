from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.runtime_worker.http_client import WorkerHttpClient
from packages.pipeline_services.legacy_media_bridge import LegacyMediaBridge
from packages.pipeline_services.legacy_schedule_bridge import LegacyScheduleBridge
from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge
from packages.runtime_adapters.mac_local import MacLocalRuntimeAdapter


class WorkerLoop:
    def __init__(
        self,
        api: Any,
        worker_id: str,
        workspace_root: Path,
        script_bridge: Any = None,
        media_bridge: Any = None,
        schedule_bridge: Any = None,
    ) -> None:
        self.api = api
        self.worker_id = worker_id
        self.workspace_root = workspace_root
        self.adapter = MacLocalRuntimeAdapter()
        self.script_bridge = script_bridge or LegacyScriptBridge(Path.cwd())
        self.media_bridge = media_bridge or LegacyMediaBridge(Path.cwd())
        self.schedule_bridge = schedule_bridge or LegacyScheduleBridge(Path.cwd() / "排期池.xlsx")

    def run_once(self) -> None:
        command = self.api.poll()
        if command["command"] == "idle":
            return

        started_at = datetime.now(timezone.utc).isoformat()
        self.adapter.ensure_tools()
        attempt_root = self.adapter.attempt_root(self.workspace_root, command["attempt_id"]).resolve()
        self.api.download_input_bundle(command["input_bundle_url"])

        job_dir = attempt_root / "output"
        job_dir.mkdir(parents=True, exist_ok=True)
        script_result = self.script_bridge.generate(product=os.environ.get("PRODUCT", "见手青"), output_dir=job_dir, mock=False)

        audio_path = job_dir / "audio.mp3"
        self.media_bridge.synthesize_tts(script_result["final_script"], audio_path)

        srt_path = job_dir / "subtitles.srt"
        self.media_bridge.build_script_timed_srt(audio_path, srt_path, script_result["final_script"])

        final_video_path = job_dir / "final.mp4"
        project_dir = (Path.cwd() / self.workspace_root / "projects" / command["project_id"]).resolve()
        base_video_path = job_dir / "base.mp4"
        self.media_bridge.build_base_video(project_dir, {"job_id": command["job_id"], "asset_bundle": {"audio_path": str(audio_path)}, "sequence": 1}, base_video_path)
        self.media_bridge.burn_final_video(base_video_path, audio_path, srt_path, final_video_path, cover_clip_path=None)

        self.schedule_bridge.append(
            command["project_id"],
            {"job_id": command["job_id"], "asset_bundle": {"post_title": "", "post_desc": "", "cover_title": ""}},
            final_video_path,
        )

        outputs = [Path(script_result["txt_path"]).resolve(), Path(script_result["json_path"]).resolve(), audio_path.resolve(), srt_path.resolve(), final_video_path.resolve()]

        uploaded_files = [
            {
                "relative_path": str(path.relative_to(attempt_root.resolve())),
                "size_bytes": path.stat().st_size,
            }
            for path in outputs
        ]
        self.api.upload_artifacts(command["task_id"], uploaded_files)

        finished_at = datetime.now(timezone.utc).isoformat()
        self.api.report(
            {
                "worker_id": self.worker_id,
                "project_id": command["project_id"],
                "job_id": command["job_id"],
                "task_id": command["task_id"],
                "attempt_id": command["attempt_id"],
                "lease_id": command["lease_id"],
                "status": "succeeded",
                "started_at": started_at,
                "finished_at": finished_at,
                "artifact_manifest": {"files": uploaded_files},
                "metrics": {},
                "logs_summary": "legacy bridges completed",
                "error": {},
            }
        )


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
    WorkerLoop(
        api=api,
        worker_id=worker_id,
        workspace_root=workspace_root,
        script_bridge=LegacyScriptBridge(root_dir),
        media_bridge=LegacyMediaBridge(root_dir),
        schedule_bridge=LegacyScheduleBridge(root_dir / "排期池.xlsx"),
    ).run_once()
