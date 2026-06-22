from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.runtime_worker.http_client import WorkerHttpClient
from apps.control_plane.services.schedule_store import ScheduleStore
from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge
from packages.pipeline_services.subtitle_service import SubtitleService
from packages.pipeline_services.tts_provider import MiMoTTSProvider, QwenTTSProvider
from packages.pipeline_services.video_service import VideoService
from packages.provider_config.app_config import AppConfigManager
from packages.runtime_adapters.mac_local import MacLocalRuntimeAdapter


class _DefaultMediaBridge:
    """使用独立 service 替代旧 LegacyMediaBridge。"""

    def __init__(self) -> None:
        self._subtitle_svc = SubtitleService()
        self._video_svc = VideoService(dry_run=False)

    def synthesize_tts(self, script_text: str, output_path: Path) -> Path:
        config = AppConfigManager()
        tts_config = config.get_tts_config()

        class _TTSConfig:
            model = tts_config.get("model", "mimo-v2.5-tts")
            voice = tts_config.get("voice", "Mia")
            instructions = tts_config.get("instructions", "")
            language_type = tts_config.get("language_type", "")
            optimize_instructions = tts_config.get("optimize_instructions", False)
            fallback_voice = tts_config.get("fallback_voice", "Dean")
            randomize_voice = tts_config.get("randomize_voice", False)
            random_voices = tts_config.get("random_voices", ["Mia", "Dean"])
            style_control_mode = tts_config.get("style_control_mode", "simple")
            style_prompt = tts_config.get("style_prompt", "自然 清晰")
            voice_design_prompt = tts_config.get("voice_design_prompt", "")
            audio_format = tts_config.get("audio_format", "wav")
            audio_tags_enabled = tts_config.get("audio_tags_enabled", False)
            audio_tags = tts_config.get("audio_tags", "")
            voice_clone_sample_path = tts_config.get("voice_clone_sample_path", "")
            voice_clone_mime_type = tts_config.get("voice_clone_mime_type", "")
            optimize_text_preview = tts_config.get("optimize_text_preview", False)
            director_character = tts_config.get("director_character", "")
            director_scene = tts_config.get("director_scene", "")
            director_guidance = tts_config.get("director_guidance", "")

        model = _TTSConfig.model or ""
        if model.startswith("qwen"):
            api_key = config.get_api_key("qwen")
            base_url = config.get_api_base_url("qwen") or "https://dashscope.aliyuncs.com/api/v1"
            provider = QwenTTSProvider(api_key=api_key, base_url=base_url)
        else:
            api_key = config.get_api_key("mimo")
            base_url = config.get_api_base_url("mimo") or "https://api.xiaomimimo.com/v1"
            provider = MiMoTTSProvider(api_key=api_key, base_url=base_url)

        audio_bytes = provider.synthesize(script_text, _TTSConfig())
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)
        return output_path

    def build_script_timed_srt(self, audio_path: Path, srt_path: Path, script_text: str) -> None:
        self._subtitle_svc.build_srt(audio_path, srt_path, script_text)

    def build_base_video(self, project_dir: Path, job_payload: dict[str, Any], output_path: Path) -> None:
        self._video_svc.build_base_video(project_dir, job_payload, output_path)

    def burn_final_video(
        self,
        base_video_path: Path,
        audio_path: Path,
        srt_path: Path | None = None,
        final_video_path: Path | None = None,
        cover_clip_path: Path | None = None,
    ) -> None:
        if final_video_path is None:
            raise TypeError("final_video_path is required")
        self._video_svc.burn_final_video(base_video_path, audio_path, srt_path, final_video_path, cover_clip_path)


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
        self.media_bridge = media_bridge or _DefaultMediaBridge()
        self.schedule_bridge = schedule_bridge or ScheduleStore(Path.cwd())

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
        language = command.get("language", "mandarin")

        if manual_script:
            final_script = manual_script
            script_path = job_dir / "script.txt"
            script_path.write_text(final_script, encoding="utf-8")
            script_json_path = job_dir / "script.json"
            script_json_path.write_text(f'{{"final_script": "{final_script}", "source": "manual"}}', encoding="utf-8")
            script_result = {"final_script": final_script, "source": "manual", "txt_path": str(script_path), "json_path": str(script_json_path)}
        else:
            script_result = self.script_bridge.generate(product=os.environ.get("PRODUCT", "荔枝菌"), output_dir=job_dir, mock=False, language=language)
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
            selected = [item for item in selected if Path(item["file_path"]).exists()]
            if selected:
                use_legacy = False
                base_video_path = job_dir / "base.mp4"
                self.media_bridge.build_base_video(
                    project_dir,
                    {
                        "job_id": command["job_id"],
                        "asset_bundle": {"audio_path": str(audio_path), "selected_clips": selected},
                        "sequence": 1,
                    },
                    base_video_path,
                )
                self.media_bridge.burn_final_video(base_video_path, audio_path, srt_path, final_video_path, cover_clip_path=None)

        if use_legacy:
            # Fallback: use legacy bridge for both build and burn
            base_video_path = job_dir / "base.mp4"
            self.media_bridge.build_base_video(project_dir, {"job_id": command["job_id"], "asset_bundle": {"audio_path": str(audio_path)}, "sequence": 1}, base_video_path)
            self.media_bridge.burn_final_video(base_video_path, audio_path, srt_path, final_video_path, cover_clip_path=None)

        self.schedule_bridge.add(
            job_id=command["job_id"],
            platform=command.get("platform", ""),
            title=command.get("product", ""),
            description="",
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
        media_bridge=_DefaultMediaBridge(),
        schedule_bridge=ScheduleStore(root_dir),
    ).run_once()
