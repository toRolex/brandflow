"""Shared media helpers used across control_plane and runtime_worker."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.provider_config.config_reader import ConfigReader


TARGET_VIDEO_WIDTH = 1080
TARGET_VIDEO_HEIGHT = 1920


class ToolNotFoundError(FileNotFoundError):
    """Raised when a required external media tool cannot be located."""

    def __init__(
        self,
        tool_name: str,
        attempted: list[str],
        suggestion: str,
    ) -> None:
        self.tool_name = tool_name
        self.attempted = attempted
        self.suggestion = suggestion
        message = (
            f"{tool_name} not found. "
            f"Attempted: {', '.join(attempted) if attempted else '(none)'}. "
            f"{suggestion}"
        )
        super().__init__(message)


def _resolve_tool_path(
    tool_name: str,
    env_var: str,
    default_candidates: list[str],
    config_path: str | None = None,
) -> str:
    """Resolve an external media tool path with a clear, actionable error.

    Resolution order:
      1. ``os.environ[env_var]`` (must exist as a file or be available in PATH)
      2. ``config_path`` (from ``app_config.json``, if provided and exists as a file)
      3. Each path in ``default_candidates`` (resolved relative to CWD)
      4. ``shutil.which(tool_name)``

    Raises
    ------
    ToolNotFoundError
        If the tool cannot be found anywhere in the search chain.
    """
    attempted: list[str] = []

    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        attempted.append(f"{env_var}={env_value}")
        if Path(env_value).exists():
            return env_value
        if shutil.which(env_value):
            return env_value

    if config_path:
        attempted.append(f"config:{config_path}")
        if Path(config_path).exists():
            return config_path

    cwd = Path.cwd()
    for candidate in default_candidates:
        path = Path(candidate)
        if not path.is_absolute():
            path = cwd / path
        attempted.append(str(path))
        if path.exists():
            return str(path)

    which_path = shutil.which(tool_name)
    if which_path:
        attempted.append(f"PATH:{which_path}")
        return which_path

    raise ToolNotFoundError(
        tool_name=tool_name,
        attempted=attempted,
        suggestion=(
            f"Set {env_var} to the executable path, place {tool_name} in "
            f"tools/bin/{tool_name}(.exe), or ensure it is available in PATH."
        ),
    )


def _resolve_ffmpeg_path(reader: ConfigReader | None = None) -> str:
    """Resolve the ffmpeg executable path.

    Priority: ``FFMPEG_PATH`` env > ``app_config.json`` media.ffmpeg_path >
    ``tools/bin/ffmpeg(.exe)`` > ``shutil.which('ffmpeg')``.
    """
    config_path: str | None = None
    if reader is not None:
        media = reader.get_media_config()
        config_path = media.get("ffmpeg_path") or None
    return _resolve_tool_path(
        tool_name="ffmpeg",
        env_var="FFMPEG_PATH",
        default_candidates=["tools/bin/ffmpeg", "tools/bin/ffmpeg.exe"],
        config_path=config_path,
    )


def _resolve_ffprobe_path(reader: ConfigReader | None = None) -> str:
    """Resolve the ffprobe executable path.

    Priority: ``FFPROBE_PATH`` env > ``app_config.json`` media.ffprobe_path >
    ``tools/bin/ffprobe(.exe)`` > ``shutil.which('ffprobe')``.
    """
    config_path: str | None = None
    if reader is not None:
        media = reader.get_media_config()
        config_path = media.get("ffprobe_path") or None
    return _resolve_tool_path(
        tool_name="ffprobe",
        env_var="FFPROBE_PATH",
        default_candidates=["tools/bin/ffprobe", "tools/bin/ffprobe.exe"],
        config_path=config_path,
    )


def _resolve_whisper_cli_path(reader: ConfigReader | None = None) -> str:
    """Resolve the whisper-cli executable path.

    Priority: ``WHISPER_CLI_PATH`` env > ``app_config.json`` media.whisper_cli_path >
    ``tools/bin/whisper-cli(.exe)`` > ``shutil.which('whisper-cli')``.
    """
    config_path: str | None = None
    if reader is not None:
        media = reader.get_media_config()
        config_path = media.get("whisper_cli_path") or None
    return _resolve_tool_path(
        tool_name="whisper-cli",
        env_var="WHISPER_CLI_PATH",
        default_candidates=["tools/bin/whisper-cli", "tools/bin/whisper-cli.exe"],
        config_path=config_path,
    )


def write_concat_file(list_path: Path, clips: list[Path]) -> None:
    list_path.parent.mkdir(parents=True, exist_ok=True)
    with list_path.open("w", encoding="utf-8") as handle:
        for clip in clips:
            escaped = str(clip).replace(chr(92), "/").replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")


def get_media_duration(file_path: Path) -> float:
    ffprobe = _resolve_ffprobe_path()
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return float(result.stdout.strip())


def normalize_clip_to_vertical(
    ffmpeg_path: str, input_path: Path, output_path: Path
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        "[0:v]split=2[bg_src][fg_src];"
        f"[bg_src]scale={TARGET_VIDEO_WIDTH}:{TARGET_VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_VIDEO_WIDTH}:{TARGET_VIDEO_HEIGHT},boxblur=20:1[bg];"
        f"[fg_src]scale={TARGET_VIDEO_WIDTH}:{TARGET_VIDEO_HEIGHT}:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
    )
    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return output_path


def assemble_vertical_base_video(
    ffmpeg_path: str,
    clip_paths: list[Path],
    audio_duration: float,
    output_path: Path,
    recipe_filter: str = "",
) -> None:
    if not clip_paths:
        raise ValueError("clip_paths must not be empty")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_path.stem}_", dir=str(output_path.parent))
    )
    normalized_paths: list[Path] = []
    concat_file = temp_dir / "concat_list.txt"

    try:
        for index, clip_path in enumerate(clip_paths):
            normalized_path = temp_dir / f"{index:03d}.mp4"
            normalize_clip_to_vertical(ffmpeg_path, clip_path, normalized_path)
            normalized_paths.append(normalized_path)

        write_concat_file(concat_file, normalized_paths)
        vf = "setsar=1"
        if recipe_filter:
            vf = f"{vf},{recipe_filter}"

        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-stream_loop",
                "-1",
                "-i",
                str(concat_file),
                "-t",
                str(audio_duration),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "superfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def get_ffmpeg_path() -> str:
    """Resolve ffmpeg executable path (backwards-compatible alias)."""
    return _resolve_ffmpeg_path()


def get_ffprobe_path() -> str:
    """Resolve ffprobe executable path (backwards-compatible alias)."""
    return _resolve_ffprobe_path()


def get_video_size(video_path: Path) -> tuple[int, int]:
    """获取视频分辨率 (width, height)。"""
    ffprobe = _resolve_ffprobe_path()
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {result.stderr}")
    parts = result.stdout.strip().split("x")
    return int(parts[0]), int(parts[1])


def _resolve_executable(
    name_or_path: str, extra_search_dirs: list[Path] | None = None
) -> str | None:
    """解析外部工具可执行文件的绝对路径。

    解析优先级：
    1. 如果是绝对路径且可执行，直接返回。
    2. 在 ``extra_search_dirs`` 中查找。
    3. 在 ``PATH`` 环境变量中查找。

    Args:
        name_or_path: 工具名称（如 ``ffmpeg``）或绝对/相对路径。
        extra_search_dirs: 额外搜索目录，优先级高于 PATH。

    Returns:
        可执行文件的绝对路径；未找到时返回 ``None``。
    """
    candidate = Path(name_or_path.strip())
    if candidate.is_absolute():
        if (
            candidate.exists()
            and candidate.is_file()
            and os.access(str(candidate), os.X_OK)
        ):
            return str(candidate.resolve())
        return None

    search_dirs: list[Path] = list(extra_search_dirs or [])
    path_env = os.environ.get("PATH", "")
    search_dirs.extend(Path(d) for d in path_env.split(os.pathsep) if d)
    if not search_dirs:
        return None

    search_path = os.pathsep.join(str(d) for d in search_dirs)
    found = shutil.which(name_or_path, path=search_path)
    if found:
        return str(Path(found).resolve())
    return None


def get_whisper_cli_path(reader: ConfigReader | None = None) -> str:
    """Resolve whisper-cli executable path.

    Priority: ``WHISPER_CLI_PATH`` env > ``ConfigReader`` media.whisper_cli_path >
    ``tools/bin/whisper-cli(.exe)`` > ``shutil.which('whisper-cli')``.

    Args:
        reader: Optional ``ConfigReader`` instance. When provided, reads
                ``media.whisper_cli_path`` from ``app_config.json`` as part
                of the resolution chain.
    """
    return _resolve_whisper_cli_path(reader=reader)


def run_ffmpeg(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """运行 ffmpeg 命令。"""
    ffmpeg = _resolve_ffmpeg_path()
    return subprocess.run(
        [ffmpeg] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
