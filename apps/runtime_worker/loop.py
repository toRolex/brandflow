from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.runtime_worker.http_client import WorkerHttpClient
from packages.pipeline_services.legacy_media_bridge import LegacyMediaBridge
from packages.pipeline_services.legacy_schedule_bridge import LegacyScheduleBridge
from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge
from packages.pipeline_services.media_utils import write_concat_file, get_media_duration
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

        manual_script = command.get("manual_script", "")
        uploaded_audio_path = command.get("uploaded_audio_path", "")

        if manual_script:
            final_script = manual_script
            script_path = job_dir / "script.txt"
            script_path.write_text(final_script, encoding="utf-8")
            script_json_path = job_dir / "script.json"
            script_json_path.write_text(f'{{"final_script": "{final_script}", "source": "manual"}}', encoding="utf-8")
            script_result = {"final_script": final_script, "source": "manual", "txt_path": str(script_path), "json_path": str(script_json_path)}
        else:
            script_result = self.script_bridge.generate(product=os.environ.get("PRODUCT", "荔枝菌"), output_dir=job_dir, mock=False)
            final_script = script_result["final_script"]

        audio_path = job_dir / "audio.mp3"
        if uploaded_audio_path:
            src_audio = Path.cwd() / uploaded_audio_path
            if src_audio.exists():
                import shutil
                shutil.copy2(src_audio, audio_path)
            else:
                self.media_bridge.synthesize_tts(final_script, audio_path)
        else:
            self.media_bridge.synthesize_tts(final_script, audio_path)

        srt_path = job_dir / "subtitles.srt"
        self.media_bridge.build_script_timed_srt(audio_path, srt_path, final_script)

        final_video_path = job_dir / "final.mp4"
        project_dir = (Path.cwd() / self.workspace_root / "projects" / command["project_id"]).resolve()

        # Use selected_clips.json if available (semantic retrieval path)
        use_legacy = True
        clip_list_path = job_dir / "selected_clips.json"
        if clip_list_path.exists():
            import json as _json
            selected = _json.loads(clip_list_path.read_text(encoding="utf-8"))
            clip_paths = [Path(item["file_path"]) for item in selected if Path(item["file_path"]).exists()]
            if clip_paths:
                use_legacy = False
                base_video_path = job_dir / "base.mp4"
                concat_list = job_dir / "concat_list.txt"
                write_concat_file(concat_list, clip_paths)
                import subprocess as _sp
                import random as _random
                audio_duration = get_media_duration(audio_path)
                ffmpeg = str(self.adapter.ffmpeg_path())
                recipes = [
                    {"vf": "eq=brightness=0.02:contrast=1.03:saturation=1.05"},
                    {"vf": "unsharp=5:5:0.8:3:3:0.4,eq=contrast=0.98"},
                    {"vf": "hflip,eq=brightness=-0.01:saturation=0.95"},
                    {"vf": "noise=alls=2:allf=t,eq=contrast=1.02"},
                ]
                recipe = recipes[hash(command["job_id"]) % 4]
                vf = f"crop=iw*{1.0 - _random.uniform(0.01, 0.03):.3f}:ih*{1.0 - _random.uniform(0.01, 0.03):.3f},scale=iw:ih,{recipe['vf']}"
                _sp.run(
                    [ffmpeg, "-f", "concat", "-safe", "0", "-i", str(concat_list),
                     "-vf", vf, "-an", "-t", f"{audio_duration:.3f}",
                     "-c:v", "libx264", "-preset", "superfast", "-crf", "23",
                     "-pix_fmt", "yuv420p", "-y", str(base_video_path)],
                    check=True, capture_output=True, text=True,
                )
                self.media_bridge.burn_final_video(base_video_path, audio_path, srt_path, final_video_path, cover_clip_path=None)

        if use_legacy:
            # Fallback: use legacy bridge for both build and burn
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
