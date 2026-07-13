"""Tests for AssetIndexer vision classification with proper failure handling (Issue #123)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from packages.pipeline_services.asset_library.indexer import (
    AssetIndexer,
    VisionClassifyError,
)
from packages.pipeline_services.asset_library.models import AssetRecord
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.pipeline_services.asset_library.vision_utils import (
    VisionConfigError,
    validate_vision_config,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_indexer(
    tmp_path: Path,
    vision_config: dict | None = None,
    product: str = "test-product",
) -> AssetIndexer:
    db_path = tmp_path / "test.db"
    repo = AssetRepository(db_path)
    if vision_config is None:
        vision_config = {
            "provider": "xiaomi",
            "endpoint": "https://vision.test.com",
            "model": "mimo-v2.5",
            "api_key": "test-key-123",
        }
    return AssetIndexer(
        ffmpeg_path="ffmpeg",
        repository=repo,
        vision_config=vision_config,
        product=product,
        category_names=["产品特写", "烹饪翻炒"],
    )


# ── Seam 5: Regression — normal classification still works ──────────────


class TestClassifyFrameSuccess:
    """Seam 5: Vision 正常返回时，_classify_frame 返回有效分类与置信度。"""

    def test_returns_category_and_confidence(self, monkeypatch):
        repo = Mock()
        indexer = AssetIndexer(
            ffmpeg_path="ffmpeg",
            repository=repo,
            vision_config={
                "provider": "xiaomi",
                "endpoint": "https://vision.test.com",
                "model": "mimo-v2.5",
                "api_key": "test-key",
            },
        )

        mock_client = Mock()
        mock_client.classify_frame.return_value = {
            "category": "烹饪翻炒",
            "confidence": 0.92,
        }
        monkeypatch.setattr(indexer, "_get_vision_client", lambda: mock_client)

        category, confidence = indexer._classify_frame(Path("frame.jpg"))
        assert category == "烹饪翻炒"
        assert confidence == 0.92

    def test_handles_lower_confidence(self, monkeypatch):
        repo = Mock()
        indexer = AssetIndexer(
            ffmpeg_path="ffmpeg",
            repository=repo,
            vision_config={
                "provider": "xiaomi",
                "endpoint": "https://vision.test.com",
                "model": "mimo-v2.5",
                "api_key": "test-key",
            },
        )

        mock_client = Mock()
        mock_client.classify_frame.return_value = {
            "category": "产品特写",
            "confidence": 0.15,
        }
        monkeypatch.setattr(indexer, "_get_vision_client", lambda: mock_client)

        category, confidence = indexer._classify_frame(Path("frame.jpg"))
        assert category == "产品特写"
        assert confidence == 0.15


# ── Seam 2: Per-clip classification failure 不应该回退到默认分类 ──────────


class TestClassifyFrameFailure:
    """Seam 2: Vision 异常时应该抛出 VisionClassifyError。"""

    def test_raises_on_timeout(self, monkeypatch):
        repo = Mock()
        indexer = AssetIndexer(
            ffmpeg_path="ffmpeg",
            repository=repo,
            vision_config={
                "provider": "xiaomi",
                "endpoint": "https://vision.test.com",
                "model": "mimo-v2.5",
                "api_key": "test-key",
            },
        )

        mock_client = Mock()
        mock_client.classify_frame.side_effect = requests.exceptions.Timeout("timeout")
        monkeypatch.setattr(indexer, "_get_vision_client", lambda: mock_client)

        with pytest.raises(VisionClassifyError, match="Timeout"):
            indexer._classify_frame(Path("frame.jpg"))

    def test_raises_on_http_error(self, monkeypatch):
        repo = Mock()
        indexer = AssetIndexer(
            ffmpeg_path="ffmpeg",
            repository=repo,
            vision_config={
                "provider": "xiaomi",
                "endpoint": "https://vision.test.com",
                "model": "mimo-v2.5",
                "api_key": "test-key",
            },
        )

        mock_client = Mock()
        resp = Mock()
        resp.status_code = 401
        resp.text = "Unauthorized"
        mock_client.classify_frame.side_effect = requests.exceptions.HTTPError(
            "401 Client Error", response=resp
        )
        monkeypatch.setattr(indexer, "_get_vision_client", lambda: mock_client)

        with pytest.raises(VisionClassifyError, match="401"):
            indexer._classify_frame(Path("frame.jpg"))

    def test_raises_on_generic_exception(self, monkeypatch):
        repo = Mock()
        indexer = AssetIndexer(
            ffmpeg_path="ffmpeg",
            repository=repo,
            vision_config={
                "provider": "xiaomi",
                "endpoint": "https://vision.test.com",
                "model": "mimo-v2.5",
                "api_key": "test-key",
            },
        )

        mock_client = Mock()
        mock_client.classify_frame.side_effect = RuntimeError("vision crashed")
        monkeypatch.setattr(indexer, "_get_vision_client", lambda: mock_client)

        with pytest.raises(VisionClassifyError, match="vision crashed"):
            indexer._classify_frame(Path("frame.jpg"))


# ── Seam 2: _ingest_one_video 在分类失败时把单个 clip 标记为 classification_failed ──


class TestIngestOneVideoClassificationFailure:
    """Seam 2: _ingest_one_video 捕获 VisionClassifyError 后应记录失败状态。"""

    def test_records_classification_failed_status(self, tmp_path, monkeypatch):
        indexer = _make_indexer(tmp_path)

        # Mock ffmpeg-dependent methods to avoid actual ffmpeg calls
        clips = [tmp_path / "clip_001.mp4"]
        clips[0].write_bytes(b"fake clip data")
        monkeypatch.setattr(indexer, "_scene_detect_and_cut", lambda v, d: clips)
        # Create the frame file and return its path
        frame_path = tmp_path / "clip_001_frame.jpg"
        frame_path.write_bytes(b"fake frame data")
        monkeypatch.setattr(indexer, "_extract_mid_frame", lambda c, d: frame_path)
        monkeypatch.setattr(indexer, "_get_duration", lambda p: 3.0)

        # 让 Vision 分类失败
        mock_client = Mock()
        mock_client.classify_frame.side_effect = RuntimeError("API unreachable")
        monkeypatch.setattr(indexer, "_get_vision_client", lambda: mock_client)

        output_base = tmp_path / "indexed"
        output_base.mkdir(parents=True)

        video_path = tmp_path / "source" / "test_video.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake video data")

        records = indexer._ingest_one_video(video_path, output_base)

        assert len(records) == 1
        record = records[0]
        assert record.status == "classification_failed", (
            f"应标记为 classification_failed，实际: {record.status}"
        )
        assert record.confidence == 0.0, "分类失败的素材 confidence 应为 0.0"
        # category 应该是最接近的兜底分类（产品特写），但 status 区分了它
        assert record.category == "产品特写"

    def test_does_not_crash_entire_video_on_single_clip_failure(
        self, tmp_path, monkeypatch
    ):
        """一个 clip 分类失败不应导致整段视频索引失败——其他 clip 仍可正常分类。"""
        indexer = _make_indexer(tmp_path)

        # 三个 clips，让第二个分类失败
        clips = [
            tmp_path / "clip_001.mp4",
            tmp_path / "clip_002.mp4",
            tmp_path / "clip_003.mp4",
        ]
        for c in clips:
            c.write_bytes(b"fake clip data")

        monkeypatch.setattr(indexer, "_scene_detect_and_cut", lambda v, d: clips)
        # Create frame files and return them by clip stem
        def _fake_extract_mid_frame(clip_path, temp_dir):
            fp = tmp_path / f"{clip_path.stem}_frame.jpg"
            fp.write_bytes(b"fake frame")
            return fp
        monkeypatch.setattr(indexer, "_extract_mid_frame", _fake_extract_mid_frame)
        monkeypatch.setattr(indexer, "_get_duration", lambda p: 3.0)

        call_count = [0]
        mock_client = Mock()

        def _classify_side_effect(_frame_path):
            call_count[0] += 1
            if call_count[0] == 2:  # second clip fails
                raise RuntimeError("API timeout")
            return {"category": "烹饪翻炒", "confidence": 0.9}

        mock_client.classify_frame.side_effect = _classify_side_effect
        monkeypatch.setattr(indexer, "_get_vision_client", lambda: mock_client)

        output_base = tmp_path / "indexed"
        output_base.mkdir(parents=True)

        video_path = tmp_path / "source" / "test_video.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"fake video data")

        records = indexer._ingest_one_video(video_path, output_base)

        # 仍然产出 3 个记录
        assert len(records) == 3
        # 第一个正常
        assert records[0].status == "available"
        assert records[0].category == "烹饪翻炒"
        # 第二个失败
        assert records[1].status == "classification_failed"
        assert records[1].confidence == 0.0
        # 第三个正常
        assert records[2].status == "available"
        assert records[2].category == "烹饪翻炒"


# ── Seam 1: Vision 配置校验 ────────────────────────────────────────────────


class TestVisionConfigValidation:
    """Seam 1: 索引开始前校验 Vision provider、endpoint、model、API key。"""

    def test_raises_on_missing_api_key(self, tmp_path):
        indexer = _make_indexer(
            tmp_path,
            vision_config={
                "provider": "xiaomi",
                "endpoint": "https://vision.test.com",
                "model": "mimo-v2.5",
                "api_key": "",
            },
        )
        with pytest.raises(VisionConfigError, match="api_key"):
            indexer._validate_vision_config()

    def test_raises_on_missing_endpoint(self, tmp_path):
        indexer = _make_indexer(
            tmp_path,
            vision_config={
                "provider": "xiaomi",
                "endpoint": "",
                "model": "mimo-v2.5",
                "api_key": "test-key",
            },
        )
        with pytest.raises(VisionConfigError, match="endpoint"):
            indexer._validate_vision_config()

    def test_raises_on_missing_model(self, tmp_path):
        indexer = _make_indexer(
            tmp_path,
            vision_config={
                "provider": "xiaomi",
                "endpoint": "https://vision.test.com",
                "model": "",
                "api_key": "test-key",
            },
        )
        with pytest.raises(VisionConfigError, match="model"):
            indexer._validate_vision_config()

    def test_raises_on_missing_provider(self, tmp_path):
        indexer = _make_indexer(
            tmp_path,
            vision_config={
                "provider": "",
                "endpoint": "https://vision.test.com",
                "model": "mimo-v2.5",
                "api_key": "test-key",
            },
        )
        with pytest.raises(VisionConfigError, match="provider"):
            indexer._validate_vision_config()

    def test_raises_on_empty_config(self, tmp_path):
        indexer = _make_indexer(tmp_path, vision_config={})
        with pytest.raises(VisionConfigError, match="provider"):
            indexer._validate_vision_config()

    def test_valid_config_does_not_raise(self, tmp_path):
        indexer = _make_indexer(
            tmp_path,
            vision_config={
                "provider": "xiaomi",
                "endpoint": "https://vision.test.com",
                "model": "mimo-v2.5",
                "api_key": "test-key-123",
            },
        )
        # Should not raise
        indexer._validate_vision_config()

    def test_ingest_videos_validates_before_processing(self, tmp_path, monkeypatch):
        """ingest_videos 应该在处理任何视频之前校验 Vision 配置。"""
        indexer = _make_indexer(tmp_path, vision_config={"provider": "xiaomi"})
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        output_base = tmp_path / "output"

        with pytest.raises(VisionConfigError, match="endpoint"):
            indexer.ingest_videos(source_dir, output_base)


# ── 公共 validate_vision_config 函数测试 ────────────────────────────────────


class TestValidateVisionConfigPublic:
    """Seam: 公共 validate_vision_config 函数校验 ConfigReader + SecretStore。"""

    def _make_valid_mocks(self):
        reader = Mock()
        reader.get_vision_config.return_value = {"provider": "xiaomi"}
        secret_store = Mock()
        secret_store.get_vision_api_key.return_value = "test-key-123"
        secret_store.get_vision_endpoint.return_value = "https://vision.test.com"
        secret_store.get_vision_model.return_value = "mimo-v2.5"
        return reader, secret_store

    def test_valid_config_passes(self):
        """配置齐全时不抛出异常。"""
        reader, secret_store = self._make_valid_mocks()
        validate_vision_config(reader, secret_store)

    def test_missing_api_key_raises(self):
        """API key 缺失时抛出 VisionConfigError。"""
        reader, secret_store = self._make_valid_mocks()
        secret_store.get_vision_api_key.return_value = ""
        with pytest.raises(VisionConfigError, match="api_key"):
            validate_vision_config(reader, secret_store)

    def test_missing_endpoint_raises(self):
        """endpoint 缺失时抛出 VisionConfigError。"""
        reader, secret_store = self._make_valid_mocks()
        secret_store.get_vision_endpoint.return_value = ""
        with pytest.raises(VisionConfigError, match="endpoint"):
            validate_vision_config(reader, secret_store)

    def test_missing_model_raises(self):
        """model 缺失时抛出 VisionConfigError。"""
        reader, secret_store = self._make_valid_mocks()
        secret_store.get_vision_model.return_value = ""
        with pytest.raises(VisionConfigError, match="model"):
            validate_vision_config(reader, secret_store)
