from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from packages.pipeline_services.asset_library.models import AssetRecord, Category
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.pipeline_services.asset_library.thumbnail import _resolve_tool_path
from packages.pipeline_services.asset_library.vision_client import VisionClient

logger = logging.getLogger(__name__)


MAX_CLIP_SECONDS = 8
SPLIT_CLIP_SECONDS = 5


FFMPEG_TIMEOUT = 300  # seconds per ffmpeg/ffprobe call


class AssetIndexer:
    def __init__(
        self,
        ffmpeg_path: str,
        repository: AssetRepository,
        vision_config: dict | None = None,
        product: str = "",
    ) -> None:
        self.ffmpeg_path = _resolve_tool_path(ffmpeg_path)
        ffprobe_path = os.environ.get("FFPROBE_PATH", ffmpeg_path.replace("ffmpeg", "ffprobe"))
        self.ffprobe_path = _resolve_tool_path(ffprobe_path)
        self.repository = repository
        self.vision_config = vision_config or {}
        self.product = product
        self._vision_client: VisionClient | None = None

    def _get_vision_client(self) -> VisionClient:
        if self._vision_client is None:
            self._vision_client = VisionClient(
                api_key=self.vision_config.get("api_key", ""),
                endpoint=self.vision_config.get("endpoint", ""),
                model=self.vision_config.get("model", ""),
                provider=self.vision_config.get("provider", ""),
            )
        return self._vision_client

    def ingest_videos(self, source_dir: Path, output_base: Path) -> list[AssetRecord]:
        output_base.mkdir(parents=True, exist_ok=True)
        records: list[AssetRecord] = []

        for video_file in sorted(source_dir.iterdir()):
            if video_file.suffix.lower() not in (".mp4", ".mov", ".avi", ".mkv"):
                continue
            records.extend(self._ingest_one_video(video_file, output_base))

        return records

    def _ingest_one_video(self, video_path: Path, output_base: Path) -> list[AssetRecord]:
        logger.info(f"[Indexer] 开始处理视频: {video_path.name}")
        temp_dir = Path(tempfile.mkdtemp(prefix="asset_cut_"))
        try:
            clips = self._scene_detect_and_cut(video_path, temp_dir)
            logger.info(f"[Indexer] 切割完成: {video_path.name} → {len(clips)} 个片段")
            records: list[AssetRecord] = []

            for i, clip_path in enumerate(clips):
                frame_path = self._extract_mid_frame(clip_path, temp_dir)
                if frame_path.exists():
                    category_name, confidence = self._classify_frame(frame_path)
                else:
                    category_name, confidence = "产品特写", 0.0
                    logger.warning(f"[Indexer] 帧提取失败，使用默认分类: {clip_path.name}")

                target_category = Category(category_name) if self._is_valid_category(category_name) else Category.MACRO
                target_dir = output_base / self.product / target_category.value
                target_dir.mkdir(parents=True, exist_ok=True)

                prefix = video_path.stem
                dest_path = target_dir / f"{prefix}_{clip_path.name}"
                if dest_path.exists():
                    dest_path = target_dir / f"{prefix}_{uuid.uuid4().hex[:6]}_{clip_path.name}"
                shutil.move(str(clip_path), str(dest_path))

                duration = self._get_duration(dest_path)
                asset_id = f"asset_{uuid.uuid4().hex[:12]}"
                now = datetime.now(timezone.utc).isoformat()

                record = AssetRecord(
                    asset_id=asset_id,
                    file_path=str(dest_path.resolve()),
                    category=target_category,
                    product=self.product,
                    confidence=confidence,
                    duration_seconds=duration,
                    status="available",
                    source_video=str(video_path.resolve()),
                    created_at=now,
                )
                self.repository.insert(record)
                records.append(record)
                logger.debug(f"[Indexer] 片段 {i+1}/{len(clips)}: {clip_path.name} → {target_category.value} (置信度: {confidence:.2f})")

            logger.info(f"[Indexer] 视频处理完成: {video_path.name} → {len(records)} 条记录")
            return records
        except Exception as e:
            logger.error(f"[Indexer] 视频处理失败: {video_path.name}, error={type(e).__name__}: {e}")
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _scene_detect_and_cut(self, video_path: Path, output_dir: Path) -> list[Path]:
        """Cut video into fixed-duration segments using stream copy (fast)."""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_pattern = str(output_dir / "clip_%03d.mp4")

        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-an",
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(MAX_CLIP_SECONDS),
            "-reset_timestamps", "1",
            "-y",
            output_pattern,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", timeout=FFMPEG_TIMEOUT)

        clips = sorted(output_dir.glob("clip_*.mp4"))

        result: list[Path] = []
        for clip in clips:
            duration = self._get_duration(clip)
            if duration > MAX_CLIP_SECONDS:
                sub_clips = self._split_long_clip(clip, output_dir)
                result.extend(sub_clips)
                clip.unlink()
            else:
                result.append(clip)

        return result

    def _split_long_clip(self, clip_path: Path, output_dir: Path) -> list[Path]:
        stem = clip_path.stem
        output_pattern = str(output_dir / f"{stem}_sub_%03d.mp4")
        cmd = [
            self.ffmpeg_path,
            "-i", str(clip_path),
            "-an",
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(SPLIT_CLIP_SECONDS),
            "-reset_timestamps", "1",
            "-y",
            output_pattern,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", timeout=FFMPEG_TIMEOUT)
        return sorted(output_dir.glob(f"{stem}_sub_*.mp4"))

    def _extract_mid_frame(self, clip_path: Path, output_dir: Path) -> Path:
        duration = self._get_duration(clip_path)
        mid_time = duration / 2.0
        frame_path = output_dir / f"{clip_path.stem}_frame.jpg"
        cmd = [
            self.ffmpeg_path,
            "-ss", f"{mid_time:.2f}",
            "-i", str(clip_path),
            "-vframes", "1",
            "-q:v", "2",
            "-y",
            str(frame_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", timeout=FFMPEG_TIMEOUT)
        return frame_path

    def _classify_frame(self, frame_path: Path) -> tuple[str, float]:
        try:
            client = self._get_vision_client()
            result = client.classify_frame(frame_path)
            return result.get("category", "产品特写"), float(result.get("confidence", 0.5))
        except Exception as exc:
            logger.error(f"[AssetIndexer] vision classify failed for {frame_path}: {exc}, falling back to 产品特写")
            return "产品特写", 0.0

    def _get_duration(self, video_path: Path) -> float:
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True,
                                encoding="utf-8", errors="ignore", timeout=FFMPEG_TIMEOUT)
        return float(result.stdout.strip())

    @staticmethod
    def _is_valid_category(name: str) -> bool:
        try:
            Category(name)
            return True
        except ValueError:
            return False
