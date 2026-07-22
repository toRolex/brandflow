"""Tests for POST /api/assets/{asset_id}/reclassify (Issue #160).

Seam 1: Asset not found -> 404.
Seam 2: Vision config invalid -> 422 vision_config_invalid.
Seam 3: Vision returns 0 confidence -> 422 zero_confidence.
Seam 4: Success path -> 200 + DB updated + no API key leak.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.pipeline_services.asset_library import AssetRecord, AssetRepository
from packages.pipeline_services.asset_library.vision_utils import VisionConfigError


def _make_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def _write_config(root_dir: Path, config: dict) -> None:
    config_dir = root_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "app_config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )


def _setup_asset(
    root_dir: Path,
    asset_id: str = "asset_reclassify_001",
    status: str = "classification_failed",
) -> tuple[Path, str, str]:
    """Create one indexed asset with a fake video file.

    Returns (db_path, asset_id, file_path).
    """
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    cat_dir = (
        root_dir
        / "workspace"
        / "shared_assets"
        / "indexed"
        / "test-product"
        / "产品特写"
    )
    cat_dir.mkdir(parents=True, exist_ok=True)
    file_path = cat_dir / "test_clip.mp4"
    file_path.write_bytes(b"fake mp4 content")

    repo = AssetRepository(db_path)
    repo.insert(
        AssetRecord(
            asset_id=asset_id,
            file_path=str(file_path.resolve()),
            category="产品特写",
            product="test-product",
            confidence=0.0,
            status=status,
        )
    )
    return db_path, asset_id, str(file_path.resolve())


def _mock_thumbnail_generate(monkeypatch) -> None:
    """Mock ThumbnailGenerator.generate to avoid real ffmpeg calls."""

    def _fake_generate(self, video_path, output_path):
        output_path.write_bytes(b"fake frame data")
        return True

    monkeypatch.setattr(
        "apps.control_plane.routes.assets.helpers.ThumbnailGenerator.generate",
        _fake_generate,
    )


def _mock_validate_vision_config_ok(monkeypatch) -> None:
    """Make validate_vision_config a no-op (config is valid)."""
    monkeypatch.setattr(
        "apps.control_plane.routes.assets.helpers.validate_vision_config",
        lambda *a, **kw: None,
    )


def _mock_classify_frame(monkeypatch, category: str, confidence: float) -> None:
    """Mock VisionClient.classify_frame to return the given result."""
    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.vision_client.VisionClient.classify_frame",
        lambda self, image_path: {"category": category, "confidence": confidence},
    )


# ── Seam 1: Asset not found ─────────────────────────────────────────────


class TestReclassifyAssetNotFound:
    """Seam 1: Asset does not exist -> 404."""

    def test_nonexistent_asset_id(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "烹饪翻炒", 0.92)

        with _make_client(tmp_path) as client:
            _setup_asset(tmp_path)

            resp = client.post("/api/assets/does_not_exist/reclassify")
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()


# ── Seam 2: Vision config invalid ───────────────────────────────────────


class TestReclassifyVisionConfigInvalid:
    """Seam 2: Vision config validation fails -> 422 vision_config_invalid."""

    def test_missing_api_key(self, tmp_path, monkeypatch) -> None:
        def _raise(*a, **kw):
            raise VisionConfigError("missing api_key")

        monkeypatch.setattr(
            "apps.control_plane.routes.assets.helpers.validate_vision_config",
            _raise,
        )

        with _make_client(tmp_path) as client:
            db_path, asset_id, _ = _setup_asset(tmp_path)

            resp = client.post(f"/api/assets/{asset_id}/reclassify")
            assert resp.status_code == 422
            assert resp.json()["detail"]["code"] == "vision_config_invalid"

    def test_empty_config(self, tmp_path, monkeypatch) -> None:
        def _raise(*a, **kw):
            raise VisionConfigError("provider, api_key")

        monkeypatch.setattr(
            "apps.control_plane.routes.assets.helpers.validate_vision_config",
            _raise,
        )

        with _make_client(tmp_path) as client:
            db_path, asset_id, _ = _setup_asset(tmp_path)

            resp = client.post(f"/api/assets/{asset_id}/reclassify")
            assert resp.status_code == 422
            assert resp.json()["detail"]["code"] == "vision_config_invalid"
            assert "provider" in resp.json()["detail"]["message"]


# ── Seam 3: Zero confidence ─────────────────────────────────────────────


class TestReclassifyZeroConfidence:
    """Seam 3: Vision returns 0 confidence -> 422 zero_confidence."""

    def test_confidence_zero_returns_error(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "产品特写", 0.0)

        with _make_client(tmp_path) as client:
            db_path, asset_id, _ = _setup_asset(tmp_path)

            resp = client.post(f"/api/assets/{asset_id}/reclassify")
            assert resp.status_code == 422
            assert resp.json()["detail"]["code"] == "zero_confidence"


# ── Seam 4: Success path ────────────────────────────────────────────────


class TestReclassifySuccess:
    """Seam 4: Valid config + valid classification -> 200 + DB updated."""

    def test_updates_asset_after_successful_classification(
        self, tmp_path, monkeypatch
    ) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "烹饪翻炒", 0.92)

        with _make_client(tmp_path) as client:
            db_path, asset_id, _ = _setup_asset(tmp_path)

            resp = client.post(f"/api/assets/{asset_id}/reclassify")

            assert resp.status_code == 200
            data = resp.json()
            assert data["asset_id"] == asset_id
            assert data["category"] == "烹饪翻炒"
            assert data["confidence"] == 0.92

            # No API key leak in response
            assert "api_key" not in json.dumps(data, ensure_ascii=False).lower()
            assert "secret" not in json.dumps(data, ensure_ascii=False).lower()
            assert "test-key" not in json.dumps(data, ensure_ascii=False).lower()

            # Verify DB was updated
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT category, confidence, status FROM assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            conn.close()
            assert row is not None
            assert row["category"] == "烹饪翻炒"
            assert row["confidence"] == 0.92
            assert row["status"] == "available"

    def test_updates_with_high_confidence(self, tmp_path, monkeypatch) -> None:
        """High confidence values are persisted correctly."""
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "成品展示", 0.99)

        with _make_client(tmp_path) as client:
            db_path, asset_id, _ = _setup_asset(tmp_path)

            resp = client.post(f"/api/assets/{asset_id}/reclassify")
            assert resp.status_code == 200
            assert resp.json()["confidence"] == 0.99

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT confidence FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            conn.close()
            assert row["confidence"] == 0.99
