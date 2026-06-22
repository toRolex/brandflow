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


# Default cover title style used when no style provided in cover_title.
DEFAULT_COVER_STYLE = {
    "primary_color": "#FFD700",
    "outline_color": "#000000",
    "highlight_color": "#FF0000",
    "outline_width": 2.0,
    "position": "center",
}


def _hex_to_ass_bgr(hex_color: str) -> str:
    """Convert #RRGGBB to ASS &HBBGGRR& format."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "&H00FFFFFF&"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H00{b}{g}{r}&"


def _ass_escape(text: str) -> str:
    """Escape ASS special characters."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _build_ass_for_cover_title(
    text: str,
    highlight_words: list[str],
    style: dict,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
    output_path: Path | None = None,
) -> Path:
    """Generate an ASS subtitle file for cover title overlay (0-duration seconds)."""
    if output_path is None:
        output_path = Path("cover_title.ass")

    primary = _hex_to_ass_bgr(style.get("primary_color", DEFAULT_COVER_STYLE["primary_color"]))
    outline = _hex_to_ass_bgr(style.get("outline_color", DEFAULT_COVER_STYLE["outline_color"]))
    highlight = _hex_to_ass_bgr(style.get("highlight_color", DEFAULT_COVER_STYLE["highlight_color"]))
    outline_width = float(style.get("outline_width", DEFAULT_COVER_STYLE["outline_width"]))
    position = style.get("position", DEFAULT_COVER_STYLE["position"])

    play_res_x = video_width
    play_res_y = video_height

    # Font size scales with video height; bold large font.
    font_size = max(int(video_height * 0.12), 48)
    margin_v = int(video_height * 0.08)
    if position == "top":
        alignment = 8  # top-center
    elif position == "bottom":
        alignment = 2  # bottom-center
    else:
        alignment = 5  # center

    # Construct body with optional highlight overrides.
    body_parts = []
    remaining = text
    highlight_lower = [w.lower() for w in highlight_words]
    for word in highlight_words:
        if not word:
            continue
        idx = remaining.lower().find(word.lower())
        if idx == -1:
            continue
        before = remaining[:idx]
        matched = remaining[idx : idx + len(word)]
        remaining = remaining[idx + len(word) :]
        if before:
            body_parts.append(_ass_escape(before))
        body_parts.append(f"{{\\c{highlight}}}{_ass_escape(matched)}{{\\c{primary}}}")
    if remaining:
        body_parts.append(_ass_escape(remaining))
    body_text = "".join(body_parts)

    ass_text = (
        "[Script Info]\n"
        "Title: Cover Title\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,sans-serif,{font_size},{primary},&H00000000&,{outline},&H00000000&,1,0,0,0,"
        f"100,100,0,0,1,{outline_width},0,{alignment},10,10,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:0{duration:.2f},Default,,0,0,0,,{body_text}\n"
    )

    output_path.write_text(ass_text, encoding="utf-8")
    return output_path


def _format_ass_path_for_ffmpeg(ass_path: Path) -> str:
    """Escape ASS path for FFmpeg subtitles filter."""
    return str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _make_music_mix_filter(
    voice_input_idx: int,
    music_input_idx: int,
    music_vol: float,
    fade_start: float,
    fade_duration: float = 1.5,
) -> str:
    return (
        f"[{voice_input_idx}:a]volume=1.0[va];"
        f"[{music_input_idx}:a]volume={music_vol:.2f},afade=t=out:st={fade_start:.3f}:d={fade_duration}[ma];"
        f"[va][ma]amix=inputs=2:duration=first:dropout_transition=0[amix]"
    )


def _build_cover_video_filter(
    cover_idx: int,
    base_idx: int,
    width: int,
    height: int,
    cover_escaped: str | None,
    has_subtitles: bool,
    srt_sub_escaped: str,
    subtitle_style: str,
) -> tuple[str, str]:
    """Build video filter chain with cover clip concatenation.

    Returns (filter_complex, video_output_label).
    Cover title takes priority over subtitles when both are present.
    """
    fc = (
        f"[{cover_idx}:v]scale={width}:{height},setsar=1[v0];"
        f"[{base_idx}:v]scale={width}:{height},setsar=1[v1];"
        f"[v0][v1]concat=n=2:v=1:a=0[cv]"
    )
    if cover_escaped is not None:
        fc += f";[cv]subtitles='{cover_escaped}':force_style='Fontname=sans-serif'[v]"
    elif has_subtitles:
        fc += f";[cv]subtitles='{srt_sub_escaped}':force_style='{subtitle_style}'[v]"
    else:
        fc += ";[cv]null[v]"
    return fc, "[v]"


def _build_simple_video_filter(
    base_idx: int,
    cover_escaped: str | None,
    has_subtitles: bool,
    srt_sub_escaped: str,
    subtitle_style: str,
) -> tuple[str, str]:
    """Build video filter chain for the no-cover-clip path.

    Returns (filter_complex, video_output_label).
    When filter_complex is empty, label is a stream spec like "0:v:0".
    Cover title and subtitles can coexist (chained) in this path.
    """
    if cover_escaped is not None:
        ct = f"subtitles='{cover_escaped}':force_style='Fontname=sans-serif'"
        if has_subtitles:
            return (
                f"[{base_idx}:v]{ct}[v];[v]subtitles='{srt_sub_escaped}':force_style='{subtitle_style}'[out]",
                "[out]",
            )
        return f"[{base_idx}:v]{ct}[v]", "[v]"
    if has_subtitles:
        return (
            f"[{base_idx}:v]subtitles='{srt_sub_escaped}':force_style='{subtitle_style}'[v]",
            "[v]",
        )
    return "", f"{base_idx}:v:0"


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
        cover_title: dict | None = None,
        music_path: Path | None = None,
        music_volume: int = 80,
    ) -> None:
        """烧录最终视频：拼接封面、混音、可选字幕与封面标题。

        Args:
            base_video_path: 基础视频路径。
            audio_path: 配音音频路径。
            srt_path: SRT 字幕路径（None 时不烧录字幕）。
            final_video_path: 最终输出路径。
            cover_clip_path: 封面片段路径（None 时不拼接封面）。
            cover_title: 封面标题数据，包含 text/highlight_words/style；视频不足 3 秒时跳过。
            music_path: 背景音乐路径（None 时不混音）。
            music_volume: 背景音乐音量百分比 0-100（默认 80）。
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
        srt_ffmpeg = _format_ass_path_for_ffmpeg(srt_path) if has_subtitles else ""

        cover_title_text = (cover_title or {}).get("text", "")
        cover_title_ass: Path | None = None
        cover_escaped: str | None = None
        if cover_title_text:
            base_duration = get_media_duration(base_video_path)
            if base_duration >= 3.0:
                width, height = get_video_size(base_video_path)
                cover_title_ass = final_video_path.parent / "cover_title.ass"
                _build_ass_for_cover_title(
                    text=cover_title_text,
                    highlight_words=(cover_title or {}).get("highlight_words", []),
                    style=(cover_title or {}).get("style", DEFAULT_COVER_STYLE),
                    video_width=width,
                    video_height=height,
                    duration=3.0,
                    output_path=cover_title_ass,
                )
                cover_escaped = _format_ass_path_for_ffmpeg(cover_title_ass)

        encoder_args = [
            "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
        ]

        has_music = music_path is not None
        music_vol = 0.0
        fade_start = 0.0
        if has_music:
            voice_duration = get_media_duration(audio_path)
            fade_start = max(0, voice_duration - 1.5)
            music_vol = music_volume / 100.0

        has_cover = cover_clip_path is not None and cover_clip_path.exists()

        # ── Build video filter ──
        if has_cover:
            width, height = get_video_size(base_video_path)
            vf, v_label = _build_cover_video_filter(
                cover_idx=0, base_idx=1,
                width=width, height=height,
                cover_escaped=cover_escaped,
                has_subtitles=has_subtitles,
                srt_sub_escaped=srt_ffmpeg,
                subtitle_style=subtitle_style,
            )
            audio_idx, music_idx = 2, 3
            inputs = ["-i", str(cover_clip_path), "-i", str(base_video_path), "-i", str(audio_path)]
        else:
            vf, v_label = _build_simple_video_filter(
                base_idx=0,
                cover_escaped=cover_escaped,
                has_subtitles=has_subtitles,
                srt_sub_escaped=srt_ffmpeg,
                subtitle_style=subtitle_style,
            )
            audio_idx, music_idx = 1, 2
            inputs = ["-i", str(base_video_path), "-i", str(audio_path)]

        # ── Build audio filter (if music) ──
        af, a_label = "", f"{audio_idx}:a:0"
        if has_music:
            af = _make_music_mix_filter(audio_idx, music_idx, music_vol, fade_start)
            a_label = "[amix]"
            inputs += ["-stream_loop", "-1", "-i", str(music_path)]

        # ── Combine filters and assemble command ──
        filter_complex = f"{vf};{af}" if vf and af else vf or af

        cmd = [ffmpeg] + inputs
        if filter_complex:
            cmd += ["-filter_complex", filter_complex, "-map", v_label, "-map", a_label]
        else:
            cmd += ["-map", v_label, "-map", a_label]
        cmd += encoder_args + [
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            "-y", str(final_video_path),
        ]

        subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
