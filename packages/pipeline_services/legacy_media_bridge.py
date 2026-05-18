from __future__ import annotations

from pathlib import Path
from typing import Any

from main_controller import PipelineController


class LegacyMediaBridge:
    def __init__(self, root_dir: Path) -> None:
        self.controller = PipelineController(
            root_dir=root_dir,
            host="127.0.0.1",
            port=0,
            batch_size=1,
            dry_run=False,
        )

    def synthesize_tts(self, script_text: str, output_path: Path) -> Path:
        return self.controller._synthesize_tts(script_text, output_path)

    def build_script_timed_srt(self, audio_path: Path, srt_path: Path, script_text: str) -> None:
        self.controller._build_script_timed_srt(audio_path, srt_path, script_text)

    def build_base_video(self, project_dir: Path, job_payload: dict[str, Any], output_path: Path) -> None:
        self.controller._build_base_video(project_dir, job_payload, output_path)

    def burn_final_video(
        self,
        base_video_path: Path,
        audio_path: Path,
        srt_path: Path,
        final_video_path: Path,
        cover_clip_path: Path | None,
    ) -> None:
        self.controller._burn_final_video(base_video_path, audio_path, srt_path, final_video_path, cover_clip_path)
