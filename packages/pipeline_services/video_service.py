"""VideoService — 视频组装与烧录。

从 PipelineController 迁移：_build_base_video / _burn_final_video
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
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
    "position": "top",
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


def _render_cover_title_png(
    text: str,
    highlight_words: list[str],
    style: dict,
    video_width: int,
    video_height: int,
    output_path: Path | None = None,
) -> Path:
    """Render cover title text as a transparent PNG using Pillow.

    Returns the path to the generated PNG image.  The image has the same
    dimensions as the video so it can be directly composited with the
    ``overlay`` filter.  Font size auto-scales so text fits within 90% of
    the video width; text wraps to two lines if needed.
    """
    from PIL import Image, ImageDraw, ImageFont

    primary = style.get("primary_color", DEFAULT_COVER_STYLE["primary_color"]).lstrip(
        "#"
    )
    highlight = style.get(
        "highlight_color", DEFAULT_COVER_STYLE["highlight_color"]
    ).lstrip("#")
    outline_color = style.get(
        "outline_color", DEFAULT_COVER_STYLE["outline_color"]
    ).lstrip("#")
    position = style.get("position", DEFAULT_COVER_STYLE["position"])

    max_w = int(video_width * 0.86)  # 86% of video width, 7% margin each side

    # Load a CJK-capable font at max size first, then auto-shrink
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]

    def _load_font(size: int):
        for fp in font_paths:
            try:
                return ImageFont.truetype(fp, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    # Auto-scale: start from max, shrink until text fits width
    font_size = max(int(video_height * 0.06), 32)
    font = _load_font(font_size)

    # Measure text width at current font size, shrink if needed
    tmp_img = Image.new("RGBA", (1, 1))
    tmp_draw = ImageDraw.Draw(tmp_img)
    text_w = tmp_draw.textlength(text, font=font)
    while text_w > max_w and font_size > 20:
        font_size = int(font_size * 0.85)
        font = _load_font(font_size)
        text_w = tmp_draw.textlength(text, font=font)

    # If still too wide, wrap into two lines at midpoint
    lines = [text]
    if text_w > max_w:
        mid = len(text) // 2
        lines = [text[:mid], text[mid:]]

    # Build segments per line: list[list[(text, color)]]
    def _build_line_segments(line_text: str) -> list[tuple[str, str]]:
        segs: list[tuple[str, str]] = []
        rem = line_text
        for word in highlight_words:
            if not word:
                continue
            idx = rem.lower().find(word.lower())
            if idx == -1:
                continue
            before = rem[:idx]
            matched = rem[idx : idx + len(word)]
            rem = rem[idx + len(word) :]
            if before:
                segs.append((before, primary))
            segs.append((matched, highlight))
        if rem:
            segs.append((rem, primary))
        return segs if segs else [(line_text, primary)]

    all_line_segments = [_build_line_segments(ln) for ln in lines]

    img = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    outline_w = int(style.get("outline_width", DEFAULT_COVER_STYLE["outline_width"]))
    or_, og, ob = (
        int(outline_color[0:2], 16),
        int(outline_color[2:4], 16),
        int(outline_color[4:6], 16),
    )

    # Measure each line
    line_heights: list[int] = []
    line_widths: list[int] = []
    for line_segs in all_line_segments:
        lh = 0
        lw = 0
        for seg_text, _ in line_segs:
            bbox = draw.textbbox((0, 0), seg_text, font=font)
            lh = max(lh, bbox[3] - bbox[1])
            lw += bbox[2] - bbox[0]
        line_heights.append(lh)
        line_widths.append(lw)

    line_spacing = int(font_size * 0.3)
    total_h = sum(line_heights) + line_spacing * (len(lines) - 1)

    if position == "top":
        y_start = int(video_height * 0.10)
    elif position == "bottom":
        y_start = video_height - int(video_height * 0.10) - total_h
    else:
        y_start = (video_height - total_h) // 2

    # Draw each line
    y = y_start
    for i, line_segs in enumerate(all_line_segments):
        x = (video_width - line_widths[i]) // 2
        for seg_text, color in line_segs:
            r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
            # Outline
            for dx in range(-outline_w, outline_w + 1):
                for dy in range(-outline_w, outline_w + 1):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text(
                        (x + dx, y + dy), seg_text, font=font, fill=(or_, og, ob, 255)
                    )
            draw.text((x, y), seg_text, font=font, fill=(r, g, b, 255))
            bbox = draw.textbbox((0, 0), seg_text, font=font)
            x += bbox[2] - bbox[0]
        y += line_heights[i] + line_spacing

    if output_path is None:
        output_path = Path("cover_title.png")
    img.save(str(output_path), "PNG")
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
    cover_title_idx: int | None,
    has_subtitles: bool,
    srt_sub_escaped: str,
    subtitle_style: str,
) -> tuple[str, str]:
    """Build video filter chain with cover clip concatenation.

    Returns (filter_complex, video_output_label).
    """
    fc = (
        f"[{cover_idx}:v]scale={width}:{height},setsar=1[v0];"
        f"[{base_idx}:v]scale={width}:{height},setsar=1[v1];"
        f"[v0][v1]concat=n=2:v=1:a=0[cv]"
    )
    if cover_title_idx is not None:
        fc += f";[cv][{cover_title_idx}:v]overlay=0:0:enable='between(t,0,3)'[v]"
    elif has_subtitles:
        fc += f";[cv]subtitles='{srt_sub_escaped}':force_style='{subtitle_style}'[v]"
    else:
        fc += ";[cv]null[v]"
    return fc, "[v]"


def _build_simple_video_filter(
    base_idx: int,
    cover_title_idx: int | None,
    has_subtitles: bool,
    srt_sub_escaped: str,
    subtitle_style: str,
) -> tuple[str, str]:
    """Build video filter chain for the no-cover-clip path.

    Returns (filter_complex, video_output_label).
    When filter_complex is empty, label is a stream spec like "0:v:0".
    Cover title (PNG overlay) and subtitles can coexist (chained) in this path.
    """
    if cover_title_idx is not None:
        overlay = (
            f"[{base_idx}:v][{cover_title_idx}:v]overlay=0:0:enable='between(t,0,3)'[v]"
        )
        if has_subtitles:
            return (
                f"{overlay};[v]subtitles='{srt_sub_escaped}':force_style='{subtitle_style}'[out]",
                "[out]",
            )
        return overlay, "[v]"
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
            clips = job.get("asset_bundle", {}).get("selected_clips", [])
            job["used_asset_ids"] = [c["asset_id"] for c in clips if c.get("asset_id")]
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

        trimmed_paths: list[Path] = []
        ffmpeg = get_ffmpeg_path()
        for i, tp in enumerate(trim_params):
            src = Path(tp["file_path"])
            trimmed = output_path.parent / f"{job['job_id']}_trim_{i:02d}.mp4"
            subprocess.run(
                [
                    ffmpeg,
                    "-ss",
                    f"{tp['ss']:.3f}",
                    "-t",
                    f"{tp['duration']:.3f}",
                    "-i",
                    str(src),
                    "-vf",
                    "fps=30,setsar=1",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-an",
                    "-y",
                    str(trimmed),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
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

        job["used_asset_ids"] = [
            c["asset_id"] for c in selected_clips if c.get("asset_id")
        ]

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
            "Fontname=Microsoft YaHei,Fontsize=12,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=2,MarginV=30,Bold=1"
        )
        has_subtitles = srt_path is not None and srt_path.exists()

        # 临时复制 SRT 到 ASCII-only 路径，避免 libass 在 Windows 上处理中文路径失败
        _srt_temp_dir: str | None = None
        if has_subtitles and any(ord(c) > 127 for c in str(srt_path)):
            _srt_temp_dir = tempfile.mkdtemp(prefix="subs_", dir=str(final_video_path.parent))
            _srt_clean_path = Path(_srt_temp_dir) / "subtitles.srt"
            shutil.copy2(srt_path, _srt_clean_path)
            srt_ffmpeg = _format_ass_path_for_ffmpeg(_srt_clean_path)
        else:
            srt_ffmpeg = _format_ass_path_for_ffmpeg(srt_path) if has_subtitles else ""

        cover_title_text = (cover_title or {}).get("text", "")
        cover_title_png: Path | None = None
        if cover_title_text:
            base_duration = get_media_duration(base_video_path)
            if base_duration >= 3.0:
                width, height = get_video_size(base_video_path)
                cover_title_png = final_video_path.parent / "cover_title.png"
                _render_cover_title_png(
                    text=cover_title_text,
                    highlight_words=(cover_title or {}).get("highlight_words", []),
                    style=(cover_title or {}).get("style", DEFAULT_COVER_STYLE),
                    video_width=width,
                    video_height=height,
                    output_path=cover_title_png,
                )

        encoder_args = [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
        ]

        has_music = music_path is not None
        music_vol = 0.0
        fade_start = 0.0
        if has_music:
            voice_duration = get_media_duration(audio_path)
            fade_start = max(0, voice_duration - 1.5)
            music_vol = music_volume / 100.0

        has_cover = cover_clip_path is not None and cover_clip_path.exists()
        has_cover_title = cover_title_png is not None and cover_title_png.exists()

        # ── Build video filter ──
        if has_cover:
            width, height = get_video_size(base_video_path)
            # cover_title_idx = 3 if both cover clip and cover title exist
            ct_idx = 3 if has_cover_title else None
            vf, v_label = _build_cover_video_filter(
                cover_idx=0,
                base_idx=1,
                width=width,
                height=height,
                cover_title_idx=ct_idx,
                has_subtitles=has_subtitles,
                srt_sub_escaped=srt_ffmpeg,
                subtitle_style=subtitle_style,
            )
            inputs = [
                "-i",
                str(cover_clip_path),
                "-i",
                str(base_video_path),
                "-i",
                str(audio_path),
            ]
            if has_cover_title:
                inputs += ["-i", str(cover_title_png)]
            audio_idx = 2
        else:
            ct_idx = 2 if has_cover_title else None
            vf, v_label = _build_simple_video_filter(
                base_idx=0,
                cover_title_idx=ct_idx,
                has_subtitles=has_subtitles,
                srt_sub_escaped=srt_ffmpeg,
                subtitle_style=subtitle_style,
            )
            inputs = ["-i", str(base_video_path), "-i", str(audio_path)]
            if has_cover_title:
                inputs += ["-i", str(cover_title_png)]
            audio_idx = 1

        # ── Build audio filter (if music) ──
        if has_music:
            inputs += ["-stream_loop", "-1", "-i", str(music_path)]
            music_idx = inputs.count("-i") - 1
            af = _make_music_mix_filter(audio_idx, music_idx, music_vol, fade_start)
            a_label = "[amix]"
        else:
            af, a_label = "", f"{audio_idx}:a:0"

        # ── Combine filters and assemble command ──
        filter_complex = f"{vf};{af}" if vf and af else vf or af

        cmd = [ffmpeg] + inputs
        if filter_complex:
            cmd += ["-filter_complex", filter_complex, "-map", v_label, "-map", a_label]
        else:
            cmd += ["-map", v_label, "-map", a_label]
        cmd += encoder_args + [
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            "-y",
            str(final_video_path),
        ]

        try:
            subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, check=True)
        finally:
            if _srt_temp_dir:
                shutil.rmtree(_srt_temp_dir, ignore_errors=True)
