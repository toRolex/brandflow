"""VideoService — 视频组装与烧录。

从 PipelineController 迁移：_build_base_video / _burn_final_video
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from packages.pipeline_services.asset_library.retriever import _compute_trim_params
from packages.pipeline_services.media_utils import (
    assemble_vertical_base_video,
    get_ffmpeg_path,
    get_media_duration,
    get_video_size,
)


class VideoService:
    """视频组装与字幕烧录服务。

    将音频 + 素材片段拼接为竖版基础视频，再烧录配音与字幕。
    """

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def build_base_video(self, project_dir: Path, job: dict, output_path: Path) -> None:
        """拼接素材片段生成基础视频。

        Args:
            project_dir: 项目目录（临时文件存放于此）。
            job: Job 字典，包含 asset_bundle -> audio_path / selected_clips。
            output_path: 输出基础视频路径。
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.dry_run:
            output_path.write_bytes(b"DRY_RUN_BASE_VIDEO")
            return

        audio_path = Path(job["asset_bundle"]["audio_path"])
        if not audio_path.exists():
            raise FileNotFoundError(f"找不到配音文件: {audio_path}")

        audio_duration = get_media_duration(audio_path)
        if audio_duration <= 0:
            raise RuntimeError(f"无法识别配音时长: {audio_path}")

        selected_clips = job.get("asset_bundle", {}).get("selected_clips", [])
        if not selected_clips:
            raise RuntimeError(f"未找到素材检索结果: {job['job_id']}")

        trim_params = _compute_trim_params(selected_clips, audio_duration)

        target_width, target_height = get_video_size(Path(selected_clips[0]["file_path"]))

        trimmed_paths: list[Path] = []
        ffmpeg = get_ffmpeg_path()
        for i, tp in enumerate(trim_params):
            src = Path(tp["file_path"])
            trimmed = output_path.parent / f"{job['job_id']}_trim_{i:02d}.mp4"
            subprocess.run(
                [
                    ffmpeg,
                    "-ss", f"{tp['ss']:.3f}",
                    "-t", f"{tp['duration']:.3f}",
                    "-i", str(src),
                    "-vf", f"scale={target_width}:{target_height},fps=30,setsar=1",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-an",
                    "-y",
                    str(trimmed),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            trimmed_paths.append(trimmed)

        try:
            assemble_vertical_base_video(
                ffmpeg_path=ffmpeg,
                clip_paths=trimmed_paths,
                audio_duration=audio_duration,
                output_path=output_path,
            )
        finally:
            for tp in trimmed_paths:
                if tp.exists():
                    tp.unlink()

    def burn_final_video(
        self,
        base_video_path: Path,
        audio_path: Path,
        srt_path: Path | None,
        final_video_path: Path,
        cover_clip_path: Path | None = None,
    ) -> None:
        """烧录最终视频：拼接封面、混音、可选字幕。

        Args:
            base_video_path: 基础视频路径。
            audio_path: 配音音频路径。
            srt_path: SRT 字幕路径（None 时不烧录字幕）。
            final_video_path: 最终输出路径。
            cover_clip_path: 封面片段路径（None 时不拼接封面）。
        """
        final_video_path.parent.mkdir(parents=True, exist_ok=True)
        if self.dry_run:
            final_video_path.write_bytes(b"DRY_RUN_FINAL_VIDEO")
            return

        ffmpeg = get_ffmpeg_path()

        subtitle_style = (
            "Fontname=sans-serif,Fontsize=12,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=2,MarginV=30,Bold=1"
        )
        has_subtitles = srt_path is not None and srt_path.exists()
        srt_ffmpeg = (
            str(srt_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            if has_subtitles
            else ""
        )

        encoder_args = [
            "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
        ]

        if cover_clip_path and cover_clip_path.exists():
            width, height = get_video_size(base_video_path)
            filter_complex = (
                f"[0:v]scale={width}:{height},setsar=1[v0];"
                f"[1:v]scale={width}:{height},setsar=1[v1];"
                f"[v0][v1]concat=n=2:v=1:a=0[cv]"
            )
            if has_subtitles:
                filter_complex += (
                    f";[cv]subtitles='{srt_ffmpeg}':force_style='{subtitle_style}'[v]"
                )
            else:
                filter_complex += ";[cv]null[v]"
            cmd = [
                ffmpeg,
                "-i", str(cover_clip_path),
                "-i", str(base_video_path),
                "-i", str(audio_path),
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "2:a:0",
                *encoder_args,
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                "-y",
                str(final_video_path),
            ]
        else:
            cmd = [
                ffmpeg,
                "-i", str(base_video_path),
                "-i", str(audio_path),
            ]
            if has_subtitles:
                cmd.extend([
                    "-vf",
                    f"subtitles='{srt_ffmpeg}':force_style='{subtitle_style}'",
                ])
            cmd.extend([
                "-map", "0:v:0",
                "-map", "1:a:0",
                *encoder_args,
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                "-y",
                str(final_video_path),
            ])

        subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
