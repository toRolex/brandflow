"""SubtitleService — SRT subtitle generation from script text and audio.

Migrated from PipelineController._build_script_timed_srt and related helpers.
Core algorithm: split text → weight-based timing → silence snapping → SRT serialization.
"""

from __future__ import annotations

import logging
import re
import subprocess
import unicodedata
from pathlib import Path

from packages.pipeline_services.media_utils import get_ffmpeg_path, get_media_duration
from packages.pipeline_services.script_service.quality import EMOJI_RE

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (same values as original PipelineController)
# ---------------------------------------------------------------------------

SUBTITLE_CHUNK_MIN_CHARS: int = 10
SUBTITLE_CHUNK_MAX_CHARS: int = 18
SUBTITLE_SILENCE_NOISE_DB: int = -35
SUBTITLE_SILENCE_MIN_SECONDS: float = 0.3
SUBTITLE_SILENCE_SNAP_SECONDS: float = 0.25

# ---------------------------------------------------------------------------
# Regexes (same patterns as original PipelineController)
# ---------------------------------------------------------------------------

SRT_ALLOWED_CHAR_RE: re.Pattern = re.compile(
    r"[^一-鿿A-Za-z0-9，。！？、；：,.!?%()\-\s" "''《》【】…·]"
)
SRT_ORPHAN_QUESTION_RE: re.Pattern = re.compile(
    r"(?<![一-鿿A-Za-z0-9])[?？]+(?![一-鿿A-Za-z0-9])"
)

# ---------------------------------------------------------------------------
# Character mapping (traditional → simplified Chinese)
# ---------------------------------------------------------------------------

TRADITIONAL_CHAR_MAP: dict = str.maketrans(
    {
        "這": "这",
        "個": "个",
        "們": "们",
        "妳": "你",
        "說": "说",
        "為": "为",
        "麼": "么",
        "裡": "里",
        "後": "后",
        "來": "来",
        "會": "会",
        "買": "买",
        "實": "实",
        "體": "体",
        "無": "无",
        "與": "与",
        "對": "对",
        "開": "开",
        "見": "见",
        "點": "点",
        "時": "时",
        "間": "间",
        "種": "种",
        "醫": "医",
        "專": "专",
        "氣": "气",
        "價": "价",
        "貼": "贴",
        "臉": "脸",
        "術": "术",
        "應": "应",
        "號": "号",
        "車": "车",
        "門": "门",
        "發": "发",
        "現": "现",
        "長": "长",
        "頭": "头",
        "臺": "台",
        "嗎": "吗",
        "讓": "让",
        "將": "将",
        "萬": "万",
        "網": "网",
        "廣": "广",
        "過": "过",
        "處": "处",
        "東": "东",
        "產": "产",
        "復": "复",
        "國": "国",
        "從": "从",
        "於": "于",
        "書": "书",
        "業": "业",
        "風": "风",
        "觸": "触",
        "覺": "觉",
        "線": "线",
        "聲": "声",
        "學": "学",
        "補": "补",
        "機": "机",
        "顏": "颜",
        "變": "变",
        "曬": "晒",
    }
)


# ---------------------------------------------------------------------------
# Package-level helper (kept as standalone for discoverability by tests)
# ---------------------------------------------------------------------------


def detect_silence_points(audio_path: Path) -> list[float]:
    """Detect silence midpoints in an audio file using ffmpeg silencedetect.

    Returns a list of midpoint times (seconds) between each silence_start / silence_end pair.
    """
    result = subprocess.run(
        [
            str(get_ffmpeg_path()),
            "-hide_banner",
            "-nostats",
            "-i",
            str(audio_path),
            "-af",
            f"silencedetect=noise={SUBTITLE_SILENCE_NOISE_DB}dB:d={SUBTITLE_SILENCE_MIN_SECONDS}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return []

    starts: list[float] = []
    ends: list[float] = []
    for line in (result.stderr or "").splitlines():
        m = re.search(r"silence_start:\s*([0-9.]+)", line)
        if m:
            starts.append(float(m.group(1)))
        m = re.search(r"silence_end:\s*([0-9.]+)", line)
        if m:
            ends.append(float(m.group(1)))

    return [(s + e) / 2 for s, e in zip(starts, ends)]


# ---------------------------------------------------------------------------
# SubtitleService
# ---------------------------------------------------------------------------


class SubtitleService:
    """Produces .srt subtitle files from script text and audio.

    Algorithm overview:
        1. Clean and sanitize the script text (strip emoji, normalize, remove markup)
        2. Split into chunks (sentence-aware, size-bounded)
        3. Assign timings proportional to visual-weight of each chunk
        4. Detect silence points from audio via ffmpeg
        5. Snap chunk boundaries to nearest silence (within tolerance)
        6. Serialize to SRT format
        7. Run a basic post-fix pass (character replacements)
    """

    # ---- public API ----

    def build_srt(self, audio_path: Path, srt_path: Path, script_text: str) -> None:
        """Build a timed .srt subtitle file from script text and audio duration.

        Raises RuntimeError if duration cannot be determined or text is empty.
        """
        duration = get_media_duration(audio_path)
        print(
            f"[SUBTITLE] Building SRT: audio={audio_path.name}"
            f" duration={duration:.2f}s script_len={len(script_text)}",
            flush=True,
        )
        if duration <= 0:
            raise RuntimeError(f"无法识别配音时长: {audio_path}")

        cleaned = self.clean_script(script_text)
        chunks = self.split_text_to_chunks(cleaned)
        if not chunks:
            raise RuntimeError("字幕原文为空")

        weights = [self.subtitle_weight(c) for c in chunks]
        total = sum(weights)

        cursor = 0.0
        blocks: list[tuple[int, float, float, str]] = []
        for idx, (chunk, w) in enumerate(zip(chunks, weights), 1):
            end = duration if idx == len(chunks) else cursor + duration * (w / total)
            blocks.append((idx, cursor, min(end, duration), chunk))
            cursor = min(end, duration)

        silence = detect_silence_points(audio_path)
        blocks = self.snap_to_silence(blocks, silence, duration)
        self.serialize_srt(blocks, srt_path)
        self.fix_srt(srt_path)

    # ---- text helpers ----

    @staticmethod
    def strip_emoji(text: str) -> str:
        return EMOJI_RE.sub("", text).strip()

    @staticmethod
    def format_srt_timestamp(seconds: float) -> str:
        total_millis = max(0, int(round(seconds * 1000)))
        millis = total_millis % 1000
        total_seconds = total_millis // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def subtitle_weight(text: str) -> int:
        visible = re.sub(r'[\s，。！？、；：,.!?%()\-\""' "《》【】…·]", "", text or "")
        return max(1, len(visible))

    # ---- sanitization ----

    def sanitize_text(self, text: str) -> str:
        """Normalize and clean a subtitle text line."""
        cleaned = unicodedata.normalize("NFKC", self.strip_emoji(text or ""))
        cleaned = cleaned.translate(TRADITIONAL_CHAR_MAP)
        for source, target in {
            "視頻": "视频",
            "這個": "这个",
            "妳": "你",
            "�": "",
        }.items():
            cleaned = cleaned.replace(source, target)
        cleaned = SRT_ALLOWED_CHAR_RE.sub("", cleaned)
        cleaned = re.sub(r"[?？]{2,}", "", cleaned)
        cleaned = SRT_ORPHAN_QUESTION_RE.sub("", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def clean_script(self, script_text: str) -> str:
        """Remove stage-direction markup from a full script before chunking."""
        cleaned = re.sub(
            r"<\s*break\b[^>]*\/?\s*>",
            "",
            script_text or "",
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\[(?:停顿|暂停|静音|pause|break)[^\]]*\]",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"（(?:停顿|暂停|静音|pause|break)[^）]*）",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\((?:停顿|暂停|静音|pause|break)[^)]*\)",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = self.sanitize_text(cleaned)
        return re.sub(r"\s+", "", cleaned).strip()

    # ---- chunking ----

    def split_text_to_chunks(
        self,
        text: str,
        min_chars: int = SUBTITLE_CHUNK_MIN_CHARS,
        max_chars: int = SUBTITLE_CHUNK_MAX_CHARS,
    ) -> list[str]:
        """Split a clean script text into subtitle-sized chunks.

        Two-pass strategy:
          1. Split on sentence-ending punctuation, then sub-split on clause
             punctuation for over-long pieces.
          2. Merge short trailing chunks into their predecessor when possible.
        """
        raw_chunks: list[str] = []
        for sentence in re.split(r"(?<=[。！？!?])", text):
            sentence = sentence.strip()
            if not sentence:
                continue
            if self.subtitle_weight(sentence) <= max_chars:
                raw_chunks.append(sentence)
                continue

            parts = [
                part.strip()
                for part in re.split(r"(?<=[，、；;：:])", sentence)
                if part.strip()
            ]
            if not parts:
                raw_chunks.append(sentence)
                continue

            buffer = ""
            for part in parts:
                if not buffer:
                    buffer = part
                    continue
                if self.subtitle_weight(buffer + part) <= max_chars:
                    buffer += part
                    continue
                raw_chunks.append(buffer)
                buffer = part
            if buffer:
                raw_chunks.append(buffer)

        # merge short tails
        merged: list[str] = []
        for chunk in raw_chunks:
            if (
                merged
                and self.subtitle_weight(merged[-1]) < min_chars
                and self.subtitle_weight(merged[-1] + chunk) <= max_chars
            ):
                merged[-1] += chunk
            else:
                merged.append(chunk)

        return [c for c in merged if c.strip()]

    # ---- timing / silence snapping ----

    def snap_to_silence(
        self,
        blocks: list[tuple[int, float, float, str]],
        silence_points: list[float],
        duration: float,
    ) -> list[tuple[int, float, float, str]]:
        """Adjust block boundaries to nearest silence midpoints (within tolerance)."""
        if len(blocks) < 2 or not silence_points:
            return blocks

        snapped = [[i, s, e, t] for i, s, e, t in blocks]
        min_gap = 0.25

        for i in range(len(snapped) - 1):
            boundary = float(snapped[i][2])
            nearest = min(
                silence_points,
                key=lambda p: abs(p - boundary),
                default=None,
            )
            if (
                nearest is None
                or abs(nearest - boundary) > SUBTITLE_SILENCE_SNAP_SECONDS
            ):
                continue
            if (
                nearest - float(snapped[i][1]) < min_gap
                or float(snapped[i + 1][2]) - nearest < min_gap
            ):
                continue
            snapped[i][2] = nearest
            snapped[i + 1][1] = nearest

        snapped[0][1] = 0.0
        snapped[-1][2] = duration

        result: list[tuple[int, float, float, str]] = []
        for i, s, e, t in snapped:
            s_f, e_f = float(s), float(e)
            if e_f <= s_f:
                if not str(t).strip():
                    continue
                e_f = s_f + 0.1
            result.append((int(i), s_f, e_f, str(t)))

        if result:
            li, ls, _, lt = result[-1]
            result[-1] = (li, ls, duration, lt)

        return result

    # ---- serialization ----

    def serialize_srt(
        self,
        blocks: list[tuple[int, float, float, str]],
        srt_path: Path,
    ) -> None:
        """Write SRT blocks to a file."""
        rendered: list[str] = []
        for index, start, end, text in blocks:
            rendered.append(
                f"{index}\n"
                f"{self.format_srt_timestamp(start)} --> {self.format_srt_timestamp(end)}\n"
                f"{text}"
            )
        srt_path.write_text("\n\n".join(rendered).strip() + "\n", encoding="utf-8")

    # ---- post-fix ----

    def fix_srt(self, srt_path: Path) -> None:
        """Post-process an SRT file: fix brand name typos and character issues."""
        if not srt_path.exists():
            return
        content = srt_path.read_text(encoding="utf-8-sig", errors="replace")
        content = content.translate(TRADITIONAL_CHAR_MAP)
        for source, target in [
            ("視頻", "视频"),
            ("這個", "这个"),
        ]:
            content = content.replace(source, target)
        srt_path.write_text(content, encoding="utf-8-sig")
