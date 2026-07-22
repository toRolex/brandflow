"""Tests for POST /api/assets/batch/reclassify (Issue #161).

Seam 1: Empty asset_ids -> 400.
Seam 2: All asset_ids don't exist -> 400.
Seam 3: Vision config invalid -> 422 vision_config_invalid.
Seam 4: Single asset via batch -> 200 + DB updated.
Seam 5: Multiple assets, all succeed -> 200 + all results.
Seam 6: Partial failures -> 200 + each item has own status/error.
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
    asset_id: str,
    status: str = "classification_failed",
) -> tuple[Path, str]:
    """Create one indexed asset with a fake video file.

    Returns (db_path, asset_id).
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
    return db_path, asset_id


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


# ── Helpers ────────────────────────────────────────────────────────────────


def _batch_reclassify(client: TestClient, asset_ids: list[str]):
    return client.post(
        "/api/assets/batch/reclassify",
        json={"asset_ids": asset_ids},
    )


# ── Seam 1: Empty asset_ids ────────────────────────────────────────────────


class TestBatchReclassifyEmptyInput:
    """Seam 1: Empty or invalid asset_ids -> 400."""

    def test_empty_array(self, tmp_path) -> None:
        with _make_client(tmp_path) as client:
            resp = _batch_reclassify(client, [])
            assert resp.status_code == 400

    def test_missing_field(self, tmp_path) -> None:
        with _make_client(tmp_path) as client:
            resp = client.post("/api/assets/batch/reclassify", json={})
            assert resp.status_code == 400


# ── Seam 2: All asset_ids don't exist ────────────────────────────────────────


class TestBatchReclassifyAllNonExistent:
    """Seam 2: All asset_ids not in DB -> 400."""

    def test_all_nonexistent(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        with _make_client(tmp_path) as client:
            # Ensure DB exists by setting up an asset, then query nonexistent IDs
            _setup_asset(tmp_path, "dummy_asset")

            resp = _batch_reclassify(client, ["no_such_1", "no_such_2"])
            assert resp.status_code == 400


# ── Seam 3: Vision config invalid ──────────────────────────────────────────


class TestBatchReclassifyVisionConfigInvalid:
    """Seam 3: Vision config validation fails -> 422."""

    def test_missing_api_key(self, tmp_path, monkeypatch) -> None:
        def _raise(*a, **kw):
            raise VisionConfigError("missing api_key")

        monkeypatch.setattr(
            "apps.control_plane.routes.assets.helpers.validate_vision_config",
            _raise,
        )

        with _make_client(tmp_path) as client:
            _setup_asset(tmp_path, "asset_001")

            resp = _batch_reclassify(client, ["asset_001"])
            assert resp.status_code == 422
            assert resp.json()["detail"]["code"] == "vision_config_invalid"


# ── Seam 4: Single asset via batch ─────────────────────────────────────────


class TestBatchReclassifySingle:
    """Seam 4: Batch with one asset -> 200 + DB updated."""

    def test_single_asset_success(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "烹饪翻炒", 0.92)

        with _make_client(tmp_path) as client:
            db_path, asset_id = _setup_asset(tmp_path, "asset_single")

            resp = _batch_reclassify(client, [asset_id])

            assert resp.status_code == 200
            results = resp.json()["results"]
            assert len(results) == 1
            assert results[0]["asset_id"] == asset_id
            assert results[0]["category"] == "烹饪翻炒"
            assert results[0]["confidence"] == 0.92
            assert results[0]["status"] == "available"

            # No API key leak
            body = json.dumps(resp.json(), ensure_ascii=False).lower()
            assert "api_key" not in body

            # Verify DB updated
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT category, confidence, status FROM assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            conn.close()
            assert row["category"] == "烹饪翻炒"
            assert row["confidence"] == 0.92
            assert row["status"] == "available"


# ── Seam 5: Multiple assets, all succeed ───────────────────────────────────


class TestBatchReclassifyMultipleSuccess:
    """Seam 5: Multiple assets all classify successfully -> 200."""

    def test_two_assets_all_succeed(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "成品展示", 0.95)

        with _make_client(tmp_path) as client:
            db_path, id1 = _setup_asset(tmp_path, "asset_m1")
            _, id2 = _setup_asset(tmp_path, "asset_m2")

            resp = _batch_reclassify(client, [id1, id2])

            assert resp.status_code == 200
            results = resp.json()["results"]
            assert len(results) == 2
            assert results[0]["asset_id"] == id1
            assert results[0]["status"] == "available"
            assert results[1]["asset_id"] == id2
            assert results[1]["status"] == "available"

            # Both assets updated in DB
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            for aid in (id1, id2):
                row = conn.execute(
                    "SELECT status FROM assets WHERE asset_id = ?", (aid,)
                ).fetchone()
                assert row["status"] == "available"
            conn.close()


# ── Seam 6: Partial failures ───────────────────────────────────────────────


class TestBatchReclassifyPartialFailure:
    """Seam 6: Some succeed, some fail -> 200 with per-item status/error."""

    def test_partial_not_found(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "烹饪翻炒", 0.92)

        with _make_client(tmp_path) as client:
            db_path, existing_id = _setup_asset(tmp_path, "existing_asset")

            resp = _batch_reclassify(client, [existing_id, "nonexistent_id"])

            assert resp.status_code == 200
            results = resp.json()["results"]
            assert len(results) == 2

            # Existing asset succeeded
            assert results[0]["asset_id"] == existing_id
            assert results[0]["status"] == "available"

            # Nonexistent has error
            assert results[1]["asset_id"] == "nonexistent_id"
            assert "error" in results[1]
            assert "not found" in results[1]["error"].lower()

            # DB only updated for existing asset
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status FROM assets WHERE asset_id = ?", (existing_id,)
            ).fetchone()
            assert row["status"] == "available"
            conn.close()

    def test_partial_zero_confidence(self, tmp_path, monkeypatch) -> None:
        """One asset gets zero confidence while another succeeds."""
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)

        # First call returns success, second returns zero confidence
        call_count = 0

        def _classify(self, image_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"category": "烹饪翻炒", "confidence": 0.92}
            return {"category": "产品特写", "confidence": 0.0}

        monkeypatch.setattr(
            "packages.pipeline_services.asset_library.vision_client.VisionClient.classify_frame",
            _classify,
        )

        with _make_client(tmp_path) as client:
            db_path, id_ok = _setup_asset(tmp_path, "asset_ok")
            _, id_zero = _setup_asset(tmp_path, "asset_zero")

            resp = _batch_reclassify(client, [id_ok, id_zero])

            assert resp.status_code == 200
            results = resp.json()["results"]
            assert len(results) == 2

            # First asset succeeded
            assert results[0]["asset_id"] == id_ok
            assert results[0]["status"] == "available"

            # Second asset has zero_confidence error
            assert results[1]["asset_id"] == id_zero
            assert "error" in results[1]

            # Only first asset updated in DB
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            row_ok = conn.execute(
                "SELECT status FROM assets WHERE asset_id = ?", (id_ok,)
            ).fetchone()
            assert row_ok["status"] == "available"
            row_zero = conn.execute(
                "SELECT status FROM assets WHERE asset_id = ?", (id_zero,)
            ).fetchone()
            assert row_zero["status"] == "classification_failed"
            conn.close()

    def test_video_file_missing(self, tmp_path, monkeypatch) -> None:
        """Asset record exists but video file on disk is gone."""
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "烹饪翻炒", 0.92)

        with _make_client(tmp_path) as client:
            db_path, asset_id = _setup_asset(tmp_path, "asset_gone")

            # Delete the video file
            cat_dir = (
                tmp_path
                / "workspace"
                / "shared_assets"
                / "indexed"
                / "test-product"
                / "产品特写"
            )
            (cat_dir / "test_clip.mp4").unlink()

            resp = _batch_reclassify(client, [asset_id])

            assert resp.status_code == 200
            results = resp.json()["results"]
            assert len(results) == 1
            assert "error" in results[0]
