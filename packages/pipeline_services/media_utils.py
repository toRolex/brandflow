"""Shared media helpers used across control_plane and runtime_worker."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from packages.provider_config.app_config import AppConfigManager


TARGET_VIDEO_WIDTH = 1080
TARGET_VIDEO_HEIGHT = 1920


def write_concat_file(list_path: Path, clips: list[Path]) -> None:
    list_path.parent.mkdir(parents=True, exist_ok=True)
    with list_path.open("w", encoding="utf-8") as handle:
        for clip in clips:
            escaped = str(clip).replace(chr(92), "/").replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")


def get_media_duration(file_path: Path) -> float:
    ffprobe = os.environ.get("FFPROBE_PATH", "ffprobe")
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
    """解析 ffmpeg 可执行文件路径。

    优先级：环境变量 FFMPEG_PATH > app_config.json media.ffmpeg_path > "ffmpeg"
    """
    import os

    env_path = os.getenv("FFMPEG_PATH", "").strip()
    if env_path:
        return env_path
    config = AppConfigManager()
    media = config.get_media_config() if hasattr(config, "get_media_config") else {}
    path = media.get("ffmpeg_path") or "ffmpeg"
    return path


def get_ffprobe_path() -> str:
    """解析 ffprobe 可执行文件路径。

    优先级：环境变量 FFPROBE_PATH > app_config.json media.ffprobe_path > "ffprobe"
    """
    import os

    env_path = os.getenv("FFPROBE_PATH", "").strip()
    if env_path:
        return env_path
    config = AppConfigManager()
    media = config.get_media_config() if hasattr(config, "get_media_config") else {}
    path = media.get("ffprobe_path") or "ffprobe"
    return path


def get_video_size(video_path: Path) -> tuple[int, int]:
    """获取视频分辨率 (width, height)。"""
    ffprobe = get_ffprobe_path()
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


def _resolve_ffmpeg_path() -> str | None:
    """解析 ffmpeg 可执行文件路径。

    优先级：环境变量/显式配置 > ``tools/bin/`` > ``PATH``。
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    tools_bin = project_root / "tools" / "bin"
    return _resolve_executable(get_ffmpeg_path(), extra_search_dirs=[tools_bin])


def _resolve_ffprobe_path() -> str | None:
    """解析 ffprobe 可执行文件路径。

    优先级：环境变量/显式配置 > ``tools/bin/`` > ``PATH``。
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    tools_bin = project_root / "tools" / "bin"
    return _resolve_executable(get_ffprobe_path(), extra_search_dirs=[tools_bin])


def get_whisper_cli_path() -> str:
    """解析 whisper-cli 可执行文件路径。

    优先级：环境变量 WHISPER_CLI_PATH > app_config.json media.whisper_cli_path > "whisper-cli"
    """
    env_path = os.getenv("WHISPER_CLI_PATH", "").strip()
    if env_path:
        return env_path
    config = AppConfigManager()
    media = config.get_media_config() if hasattr(config, "get_media_config") else {}
    path = media.get("whisper_cli_path") or "whisper-cli"
    return path


def _resolve_whisper_cli_path() -> str | None:
    """解析 whisper-cli 可执行文件路径。

    优先级：环境变量/显式配置 > ``tools/bin/`` > ``PATH``。
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    tools_bin = project_root / "tools" / "bin"
    return _resolve_executable(get_whisper_cli_path(), extra_search_dirs=[tools_bin])


def run_ffmpeg(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """运行 ffmpeg 命令。"""
    ffmpeg = get_ffmpeg_path()
    return subprocess.run(
        [ffmpeg] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
