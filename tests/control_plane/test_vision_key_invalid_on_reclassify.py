"""Tests for 401/403 Vision key errors mapped to 422 vision_key_invalid (Issue #156)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import requests

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.pipeline_services.asset_library import AssetRecord, AssetRepository


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
    asset_id: str = "asset_001",
    status: str = "classification_failed",
    category: str = "产品特写",
    confidence: float = 0.0,
) -> Path:
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    cat_dir = (
        root_dir / "workspace" / "shared_assets" / "indexed" / "test-product" / category
    )
    cat_dir.mkdir(parents=True, exist_ok=True)
    file_path = cat_dir / "test_clip.mp4"
    file_path.write_bytes(b"fake mp4 content")

    repo = AssetRepository(db_path)
    repo.insert(
        AssetRecord(
            asset_id=asset_id,
            file_path=str(file_path.resolve()),
            category=category,
            product="test-product",
            confidence=confidence,
            status=status,
        )
    )
    return db_path


def _mock_validate_vision_config_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.validate_vision_config",
        lambda *a, **kw: None,
    )


def _mock_thumbnail_generate(monkeypatch) -> None:
    def _fake_generate(self, video_path, output_path):
        output_path.write_bytes(b"fake frame data")
        return True

    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.ThumbnailGenerator.generate",
        _fake_generate,
    )


def _make_http_error(status_code: int) -> requests.exceptions.HTTPError:
    resp = Mock()
    resp.status_code = status_code
    resp.text = "invalid key"
    return requests.exceptions.HTTPError(f"{status_code} Client Error", response=resp)


def _classify_raises(status_code: int):
    err = _make_http_error(status_code)

    def _fn(self, image_path):
        raise err

    return _fn


class TestReclassifyVisionKeyInvalid:
    """POST /api/assets/{asset_id}/reclassify -> 422 on 401/403."""

    def test_401_returns_vision_key_invalid(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        monkeypatch.setattr(
            "packages.pipeline_services.asset_library.vision_client.VisionClient.classify_frame",
            _classify_raises(401),
        )

        client = _make_client(tmp_path)
        _setup_asset(tmp_path)
        asset_id = "asset_001"

        resp = client.post(f"/api/assets/{asset_id}/reclassify")
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "vision_key_invalid"

    def test_403_returns_vision_key_invalid(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        monkeypatch.setattr(
            "packages.pipeline_services.asset_library.vision_client.VisionClient.classify_frame",
            _classify_raises(403),
        )

        client = _make_client(tmp_path)
        _setup_asset(tmp_path)
        asset_id = "asset_001"

        resp = client.post(f"/api/assets/{asset_id}/reclassify")
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "vision_key_invalid"


class TestEnableAutoReclassifyVisionKeyInvalid:
    """PATCH /api/assets/{asset_id} status=available -> 422 on 401/403."""

    def test_401_returns_vision_key_invalid(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        monkeypatch.setattr(
            "packages.pipeline_services.asset_library.vision_client.VisionClient.classify_frame",
            _classify_raises(401),
        )

        client = _make_client(tmp_path)
        _setup_asset(tmp_path, status="classification_failed")

        resp = client.patch("/api/assets/asset_001", json={"status": "available"})
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "vision_key_invalid"


class TestBatchEnableVisionKeyInvalid:
    """PATCH /api/assets/batch status=available -> 422 on 401/403."""

    def test_401_returns_vision_key_invalid(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        monkeypatch.setattr(
            "packages.pipeline_services.asset_library.vision_client.VisionClient.classify_frame",
            _classify_raises(401),
        )

        client = _make_client(tmp_path)
        _setup_asset(tmp_path, status="classification_failed")

        resp = client.patch(
            "/api/assets/batch",
            json={"asset_ids": ["asset_001"], "status": "available"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "vision_key_invalid"


class TestBatchReclassifyVisionKeyInvalid:
    """POST /api/assets/batch/reclassify -> per-item error on 401/403."""

    def test_401_returns_per_item_error(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        monkeypatch.setattr(
            "packages.pipeline_services.asset_library.vision_client.VisionClient.classify_frame",
            _classify_raises(401),
        )

        client = _make_client(tmp_path)
        db_path = _setup_asset(tmp_path, "asset_001")
        asset_id = "asset_001"

        resp = client.post(
            "/api/assets/batch/reclassify",
            json={"asset_ids": [asset_id]},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["asset_id"] == asset_id
        assert results[0]["error"] == "vision_key_invalid"

        # DB should remain unchanged
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT status FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        conn.close()
        assert row[0] == "classification_failed"
