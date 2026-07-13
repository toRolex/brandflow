"""Tests for Phase 2 Slice 7 — AI-powered Category Suggestion."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from packages.pipeline_services.asset_library.category_suggestion import (
    _describe_frame_with_vision,
    _extract_frame,
    _get_media_duration,
    _resolve_vision_api_config,
    suggest_categories,
)


@pytest.fixture
def empty_db_dir() -> Path:
    """A directory with NO asset_index.db."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def populated_db_dir() -> Path:
    """A directory with a populated asset_index.db."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        db_dir = root / "workspace" / "shared_assets"
        db_dir.mkdir(parents=True)
        db_path = db_dir / "asset_index.db"

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                category TEXT NOT NULL,
                product TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.0,
                duration_seconds REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'available',
                usage_count INTEGER NOT NULL DEFAULT 0,
                source_video TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT '',
                last_used_at TEXT NOT NULL DEFAULT ''
            )"""
        )

        # Insert some test assets
        for i in range(5):
            video_path = root / f"test_video_{i}.mp4"
            video_path.write_text("fake video content")
            conn.execute(
                """INSERT INTO assets
                   (asset_id, file_path, category, product, duration_seconds, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'available', '2025-01-01T00:00:00')""",
                (f"asset_{i}", str(video_path), "产品特写", "test_product", 10.0),
            )

        conn.commit()
        conn.close()
        yield root


def test_empty_asset_db(empty_db_dir: Path) -> None:
    """suggest_categories should handle missing database gracefully."""
    result = suggest_categories(root_dir=empty_db_dir, sample_size=10)

    assert result["categories"] == []
    assert result["sampled_assets"] == 0
    assert len(result["errors"]) >= 1
    assert "not found" in result["errors"][0].lower()


def test_empty_library() -> None:
    """suggest_categories should handle empty asset library."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        db_dir = root / "workspace" / "shared_assets"
        db_dir.mkdir(parents=True)
        db_path = db_dir / "asset_index.db"

        # Create empty table
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                category TEXT NOT NULL,
                product TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.0,
                duration_seconds REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'available',
                usage_count INTEGER NOT NULL DEFAULT 0,
                source_video TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT '',
                last_used_at TEXT NOT NULL DEFAULT ''
            )"""
        )
        conn.commit()
        conn.close()

        result = suggest_categories(root_dir=root, sample_size=10)

        assert result["categories"] == []
        assert result["sampled_assets"] == 0
        assert len(result["errors"]) >= 1


@patch(
    "packages.pipeline_services.asset_library.category_suggestion._resolve_vision_api_config"
)
@patch(
    "packages.pipeline_services.asset_library.category_suggestion._resolve_llm_api_config"
)
@patch("packages.pipeline_services.asset_library.category_suggestion._extract_frame")
@patch(
    "packages.pipeline_services.asset_library.category_suggestion._describe_frame_with_vision"
)
@patch(
    "packages.pipeline_services.asset_library.category_suggestion._cluster_descriptions"
)
def test_suggest_categories_full_flow(
    mock_cluster: Mock,
    mock_describe: Mock,
    mock_extract: Mock,
    mock_llm_config: Mock,
    mock_vision_config: Mock,
    populated_db_dir: Path,
) -> None:
    """Full flow with mocked vision and LLM calls should return suggested categories."""
    # Mock API configs
    mock_vision_config.return_value = {
        "provider": "xiaomi",
        "api_key": "test-vision-key",
        "endpoint": "https://vision.test/chat/completions",
        "model": "mimo-v2.5",
    }
    mock_llm_config.return_value = {
        "provider": "deepseek",
        "api_key": "test-llm-key",
        "endpoint": "https://llm.test/chat/completions",
        "model": "deepseek-v4-flash",
    }

    # Mock frame extraction — return a fake path
    fake_frame = populated_db_dir / "frame.jpg"
    fake_frame.write_text("fake")
    mock_extract.return_value = fake_frame

    # Mock vision descriptions
    mock_describe.side_effect = [
        "产品在展台上展示，特写镜头",
        "工人正在筛选原材料",
        "烹饪过程中翻炒的画面",
        "成品装盘，摆盘精致",
        "试吃品尝环节",
    ]

    # Mock LLM clustering
    mock_cluster.return_value = [
        {
            "id": "product_display",
            "name": "产品展示",
            "description": "产品特写和展示镜头",
            "vision_prompt": "Identify close-up shots of products",
        },
        {
            "id": "processing",
            "name": "加工处理",
            "description": "原材料筛选和加工",
            "vision_prompt": "Identify processing and sorting activities",
        },
        {
            "id": "cooking",
            "name": "烹饪制作",
            "description": "烹饪翻炒和制作过程",
            "vision_prompt": "Identify cooking and stir-frying scenes",
        },
        {
            "id": "plating",
            "name": "出锅装盘",
            "description": "成品装盘展示",
            "vision_prompt": "Identify plated finished dishes",
        },
        {
            "id": "tasting",
            "name": "试吃品尝",
            "description": "试吃和品尝环节",
            "vision_prompt": "Identify tasting and eating scenes",
        },
    ]

    with patch.dict("os.environ", {"PRODUCT": "test_product"}):
        result = suggest_categories(
            root_dir=populated_db_dir,
            sample_size=5,
        )

    assert len(result["categories"]) == 5
    assert result["sampled_assets"] == 5
    assert result["model_used"] == "deepseek-v4-flash"
    assert len(result["errors"]) == 0
    assert len(result["descriptions"]) == 5

    # Check category structure
    first = result["categories"][0]
    assert "id" in first
    assert "name" in first
    assert "description" in first
    assert "vision_prompt" in first

    # Verify the LLM clustering was called
    mock_cluster.assert_called_once()


@patch(
    "packages.pipeline_services.asset_library.category_suggestion._cluster_descriptions"
)
def test_suggest_no_vision_results(
    mock_cluster: Mock,
    populated_db_dir: Path,
) -> None:
    """When vision API returns no descriptions, should return empty categories."""
    with patch(
        "packages.pipeline_services.asset_library.category_suggestion._resolve_vision_api_config"
    ) as mock_vision:
        mock_vision.return_value = {
            "provider": "xiaomi",
            "api_key": "test-key",
            "endpoint": "https://vision.test/chat/completions",
            "model": "mimo-v2.5",
        }
        with patch(
            "packages.pipeline_services.asset_library.category_suggestion._resolve_llm_api_config"
        ) as mock_llm:
            mock_llm.return_value = {
                "provider": "deepseek",
                "api_key": "test-key",
                "endpoint": "https://llm.test/chat/completions",
                "model": "deepseek-v4-flash",
            }
            # Mock frame extraction to return None (all fail)
            with patch(
                "packages.pipeline_services.asset_library.category_suggestion._extract_frame"
            ) as mock_extract:
                mock_extract.return_value = None
                with patch.dict("os.environ", {"PRODUCT": "test_product"}):
                    result = suggest_categories(
                        root_dir=populated_db_dir,
                        sample_size=5,
                    )

    assert result["categories"] == []
    assert result["sampled_assets"] == 5
    assert len(result["errors"]) > 0
    mock_cluster.assert_not_called()


@patch(
    "packages.pipeline_services.asset_library.category_suggestion._resolve_vision_api_config"
)
@patch(
    "packages.pipeline_services.asset_library.category_suggestion._resolve_llm_api_config"
)
@patch("packages.pipeline_services.asset_library.category_suggestion._extract_frame")
@patch(
    "packages.pipeline_services.asset_library.category_suggestion._describe_frame_with_vision"
)
@patch(
    "packages.pipeline_services.asset_library.category_suggestion._cluster_descriptions"
)
def test_suggest_with_fewer_assets_than_sample(
    mock_cluster: Mock,
    mock_describe: Mock,
    mock_extract: Mock,
    mock_llm_config: Mock,
    mock_vision_config: Mock,
    populated_db_dir: Path,
) -> None:
    """When there are fewer assets than sample_size, should sample all."""
    mock_vision_config.return_value = {
        "provider": "xiaomi",
        "api_key": "test-key",
        "endpoint": "https://vision.test/chat/completions",
        "model": "mimo-v2.5",
    }
    mock_llm_config.return_value = {
        "provider": "deepseek",
        "api_key": "test-key",
        "endpoint": "https://llm.test/chat/completions",
        "model": "deepseek-v4-flash",
    }

    fake_frame = populated_db_dir / "frame.jpg"
    fake_frame.write_text("fake")
    mock_extract.return_value = fake_frame
    mock_describe.return_value = "A test scene description"
    mock_cluster.return_value = [
        {
            "id": "general",
            "name": "通用分类",
            "description": "通用场景",
            "vision_prompt": "General scene",
        }
    ]

    with patch.dict("os.environ", {"PRODUCT": "test_product"}):
        result = suggest_categories(
            root_dir=populated_db_dir,
            sample_size=100,  # larger than our 5 assets
        )

    # Should only sample 5 (all available)
    assert result["sampled_assets"] == 5
    assert len(result["categories"]) == 1


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------


class TestExtractFrame:
    def test_extract_frame_nonexistent_video(self) -> None:
        """Extracting a frame from a nonexistent video should return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _extract_frame(
                video_path=Path("/nonexistent/video.mp4"),
                output_dir=Path(tmpdir),
            )
        assert result is None

    def test_extract_frame_not_a_video(self) -> None:
        """Extracting from a non-video file should return None (ffmpeg fails)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_video = Path(tmpdir) / "fake.mp4"
            fake_video.write_text("not a real video")
            result = _extract_frame(
                video_path=fake_video,
                output_dir=tmpdir,
            )
        assert result is None


class TestGetMediaDuration:
    def test_nonexistent_file(self) -> None:
        """ffprobe on a nonexistent file should return None."""
        result = _get_media_duration(Path("/nonexistent/file.mp4"))
        assert result is None

    def test_not_a_video(self) -> None:
        """ffprobe on a non-video file should return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake = Path(tmpdir) / "fake.mp4"
            fake.write_text("not a video")
            result = _get_media_duration(fake)
            assert result is None


class TestDescribeFrameWithVision:
    def test_vision_api_failure(self) -> None:
        """Vision API failure should return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            img = Path(tmpdir) / "test.jpg"
            img.write_text("fake image data")
            result = _describe_frame_with_vision(
                image_path=img,
                api_key="test-key",
                endpoint="https://api.example.com/chat/completions",
                model="test-model",
            )
            # Will fail because the endpoint is fake — should return None
            assert result is None


class TestResolveVisionConfig:
    def test_returns_dict_with_keys(self) -> None:
        """resolve_vision_api_config should return a dict with expected keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_path = config_dir / "app_config.json"
            config_path.write_text(
                json.dumps(
                    {"vision": {"provider": "xiaomi", "model": "mimo-v2.5"}},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with (
                patch(
                    "packages.pipeline_services.asset_library.category_suggestion.ConfigReader"
                ) as MockReader,
                patch(
                    "packages.pipeline_services.asset_library.category_suggestion.SecretStore"
                ) as MockSecrets,
            ):
                mock_reader = MockReader.return_value
                mock_reader.get_vision_config.return_value = {
                    "provider": "xiaomi",
                    "model": "mimo-v2.5",
                }
                mock_secrets = MockSecrets.return_value
                mock_secrets.get_vision_api_key.return_value = "test-key"
                mock_secrets.get_vision_endpoint.return_value = (
                    "https://vision.test/chat/completions"
                )
                mock_secrets.get_vision_model.return_value = "mimo-v2.5"

                config = _resolve_vision_api_config()

            assert "provider" in config
            assert "api_key" in config
            assert "endpoint" in config
            assert "model" in config


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(populated_db_dir: Path) -> object:
    """Create a FastAPI TestClient with mocked root_dir."""
    from fastapi.testclient import TestClient

    from apps.control_plane.app import create_app

    app = create_app(root_dir=populated_db_dir)
    return TestClient(app)


class TestSuggestEndpoint:
    @patch("apps.control_plane.routes.category_suggestion.suggest_categories")
    def test_suggest_endpoint_post(
        self,
        mock_suggest: Mock,
        api_client: object,
    ) -> None:
        """POST /api/assets/categories/suggest should return suggested categories."""
        client = api_client

        mock_suggest.return_value = {
            "categories": [
                {
                    "id": "product_display",
                    "name": "产品展示",
                    "description": "产品特写镜头",
                    "vision_prompt": "Detect product close-ups",
                }
            ],
            "sampled_assets": 5,
            "model_used": "deepseek-v4-flash",
            "descriptions": ["desc1", "desc2"],
            "errors": [],
        }

        response = client.post(
            "/api/assets/categories/suggest",
            json={"sample_size": 5},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["suggestions"]) == 1
        assert data["sampled_assets"] == 5
        assert data["errors"] == []

    @patch("apps.control_plane.routes.category_suggestion.suggest_categories")
    def test_suggest_endpoint_with_model_override(
        self,
        mock_suggest: Mock,
        api_client: object,
    ) -> None:
        """POST with custom model should pass model override to service."""
        client = api_client

        mock_suggest.return_value = {
            "categories": [],
            "sampled_assets": 0,
            "model_used": "custom-model",
            "descriptions": [],
            "errors": [],
        }

        response = client.post(
            "/api/assets/categories/suggest",
            json={"sample_size": 10, "model": "custom-model"},
        )

        assert response.status_code == 200

    def test_suggest_endpoint_empty_db(self, empty_db_dir: Path) -> None:
        """POST to suggest with no asset DB should return empty result."""
        from fastapi.testclient import TestClient

        from apps.control_plane.app import create_app

        app = create_app(root_dir=empty_db_dir)
        client = TestClient(app)

        response = client.post(
            "/api/assets/categories/suggest",
            json={"sample_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["suggestions"] == []
        assert data["sampled_assets"] == 0
        assert len(data["errors"]) > 0

    def test_suggest_rejects_invalid_body(self, api_client: object) -> None:
        """POST with invalid body should return 422."""
        client = api_client
        response = client.post(
            "/api/assets/categories/suggest",
            json={"sample_size": "not_a_number"},  # invalid type
        )
        assert response.status_code == 422

    def test_suggest_rejects_empty_body(self, api_client: object) -> None:
        """POST with empty JSON body should work (all defaults)."""
        client = api_client

        with patch(
            "apps.control_plane.routes.category_suggestion.suggest_categories"
        ) as mock_suggest:
            mock_suggest.return_value = {
                "categories": [],
                "sampled_assets": 0,
                "model_used": "deepseek-v4-flash",
                "descriptions": [],
                "errors": [],
            }

            response = client.post(
                "/api/assets/categories/suggest",
                json={},
            )

            assert response.status_code == 200
