"""Tests for auto-reclassify on enable (Issue #162).

PATCH /api/assets/{asset_id} and PATCH /api/assets/batch must auto-trigger
reclassification when status=available and the asset needs it (classification_failed,
confidence <= 0, or category not in active product category list).

Seams tested:
1. Single enable on classification_failed asset -> reclassify succeeds -> 200
2. Single enable on confidence=0 asset -> reclassify succeeds -> 200
3. Single enable on invalid-category asset -> reclassify succeeds -> 200
4. Vision returns 0 confidence -> 422 zero_confidence
5. Vision config invalid -> 422 vision_config_invalid
6. Vision returns category not in active list -> 422 unknown_category
7. Already-good asset (confidence>0, valid category) -> direct update, no reclassify
8. status=disabled -> no reclassify, direct update
9. status=pending_review -> no reclassify, direct update
10. Batch enable: all need reclassify and pass -> all updated
11. Batch enable: some fail reclassify -> 422
12. Batch enable: no reclassify needed -> simple batch update
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.pipeline_services.asset_library import AssetRecord, AssetRepository
from packages.pipeline_services.asset_library.vision_utils import VisionConfigError


# ── Helpers ────────────────────────────────────────────────────────────────


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
    asset_id: str = "auto_reclassify_001",
    status: str = "classification_failed",
    category: str = "产品特写",
    confidence: float = 0.0,
) -> Path:
    """Create one indexed asset with a fake video file.

    Returns db_path.
    """
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


# ── Single asset: classification_failed -> reclassify -> 200 ──────────────


class TestSingleEnableTriggersReclassify:
    """When PATCH status=available on a failing asset, auto-reclassify runs."""

    def test_classification_failed_triggers_reclassify(
        self, tmp_path, monkeypatch
    ) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "烹饪翻炒", 0.92)

        client = _make_client(tmp_path)
        db_path = _setup_asset(tmp_path, status="classification_failed")

        resp = client.patch(
            "/api/assets/auto_reclassify_001", json={"status": "available"}
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, category, confidence FROM assets WHERE asset_id = ?",
            ("auto_reclassify_001",),
        ).fetchone()
        conn.close()
        assert row["status"] == "available"
        assert row["category"] == "烹饪翻炒"
        assert row["confidence"] == 0.92

    def test_zero_confidence_triggers_reclassify(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "成品展示", 0.99)

        client = _make_client(tmp_path)
        db_path = _setup_asset(
            tmp_path, status="available", confidence=0.0, category="产品特写"
        )

        resp = client.patch(
            "/api/assets/auto_reclassify_001", json={"status": "available"}
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, category, confidence FROM assets WHERE asset_id = ?",
            ("auto_reclassify_001",),
        ).fetchone()
        conn.close()
        assert row["status"] == "available"
        assert row["confidence"] == 0.99

    def test_invalid_category_triggers_reclassify(self, tmp_path, monkeypatch) -> None:
        """Asset with category not in active list triggers reclassify."""
        _write_config(
            tmp_path,
            {
                "asset_library": {
                    "categories": [
                        {"id": "promo", "name": "促销活动"},
                        {"id": "unboxing", "name": "开箱展示"},
                    ]
                }
            },
        )
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "开箱展示", 0.88)

        client = _make_client(tmp_path)
        # Asset has "产品特写" which is NOT in the active list
        db_path = _setup_asset(
            tmp_path, status="available", confidence=0.85, category="产品特写"
        )

        resp = client.patch(
            "/api/assets/auto_reclassify_001", json={"status": "available"}
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT category, confidence FROM assets WHERE asset_id = ?",
            ("auto_reclassify_001",),
        ).fetchone()
        conn.close()
        assert row["category"] == "开箱展示"


# ── Single asset: reclassify failure paths ────────────────────────────────


class TestSingleEnableReclassifyFails:
    """When auto-reclassify fails, the PATCH must reject with 422."""

    def test_vision_returns_zero_confidence(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "产品特写", 0.0)

        client = _make_client(tmp_path)
        _setup_asset(tmp_path, status="classification_failed")

        resp = client.patch(
            "/api/assets/auto_reclassify_001", json={"status": "available"}
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "zero_confidence"

    def test_vision_config_invalid(self, tmp_path, monkeypatch) -> None:
        def _raise(*a, **kw):
            raise VisionConfigError("missing api_key")

        monkeypatch.setattr(
            "apps.control_plane.routes.assets.helpers.validate_vision_config",
            _raise,
        )

        client = _make_client(tmp_path)
        _setup_asset(tmp_path, status="classification_failed")

        resp = client.patch(
            "/api/assets/auto_reclassify_001", json={"status": "available"}
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "vision_config_invalid"

    def test_vision_returns_unknown_category(self, tmp_path, monkeypatch) -> None:
        _write_config(
            tmp_path,
            {
                "asset_library": {
                    "categories": [
                        {"id": "promo", "name": "促销活动"},
                        {"id": "unboxing", "name": "开箱展示"},
                    ]
                }
            },
        )
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        # Vision returns a category NOT in the active list
        _mock_classify_frame(monkeypatch, "不存在的分类", 0.85)

        client = _make_client(tmp_path)
        _setup_asset(tmp_path, status="classification_failed")

        resp = client.patch(
            "/api/assets/auto_reclassify_001", json={"status": "available"}
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "unknown_category"
        assert "不存在的分类" in detail["message"]


# ── Single asset: no reclassify needed ────────────────────────────────────


class TestSingleEnableNoReclassify:
    """When asset is already good, PATCH does a simple status update."""

    def test_already_good_asset(self, tmp_path, monkeypatch) -> None:
        """Asset with confidence>0 and valid category -> no reclassify."""
        client = _make_client(tmp_path)
        db_path = _setup_asset(
            tmp_path, status="available", confidence=0.95, category="产品特写"
        )

        resp = client.patch(
            "/api/assets/auto_reclassify_001", json={"status": "available"}
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

        # Should NOT have triggered reclassify (confidence unchanged)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, confidence FROM assets WHERE asset_id = ?",
            ("auto_reclassify_001",),
        ).fetchone()
        conn.close()
        assert row["status"] == "available"
        assert row["confidence"] == 0.95

    def test_status_disabled_no_reclassify(self, tmp_path, monkeypatch) -> None:
        client = _make_client(tmp_path)
        db_path = _setup_asset(tmp_path, status="classification_failed", confidence=0.0)

        resp = client.patch(
            "/api/assets/auto_reclassify_001", json={"status": "disabled"}
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM assets WHERE asset_id = ?",
            ("auto_reclassify_001",),
        ).fetchone()
        conn.close()
        assert row["status"] == "disabled"

    def test_status_pending_review_no_reclassify(self, tmp_path, monkeypatch) -> None:
        client = _make_client(tmp_path)
        db_path = _setup_asset(tmp_path, status="classification_failed", confidence=0.0)

        resp = client.patch(
            "/api/assets/auto_reclassify_001", json={"status": "pending_review"}
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM assets WHERE asset_id = ?",
            ("auto_reclassify_001",),
        ).fetchone()
        conn.close()
        assert row["status"] == "pending_review"

    def test_asset_not_found_404(self, tmp_path, monkeypatch) -> None:
        client = _make_client(tmp_path)
        _setup_asset(tmp_path)

        resp = client.patch("/api/assets/does_not_exist", json={"status": "available"})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ── Batch enable ──────────────────────────────────────────────────────────


def _setup_multi_asset(root_dir: Path, n: int = 3) -> tuple[Path, list[str]]:
    """Create *n* assets: first needs reclassify, rest are good.

    Returns (db_path, asset_ids).
    """
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    asset_ids = []
    for i in range(n):
        aid = f"batch_asset_{i:03d}"
        asset_ids.append(aid)
        cat_dir = (
            root_dir
            / "workspace"
            / "shared_assets"
            / "indexed"
            / "test-product"
            / "产品特写"
        )
        cat_dir.mkdir(parents=True, exist_ok=True)
        file_path = cat_dir / f"{aid}.mp4"
        file_path.write_bytes(b"fake mp4 content")

        repo = AssetRepository(db_path)
        status = "classification_failed" if i == 0 else "available"
        confidence = 0.0 if i == 0 else 0.95
        repo.insert(
            AssetRecord(
                asset_id=aid,
                file_path=str(file_path.resolve()),
                category="产品特写",
                product="test-product",
                confidence=confidence,
                status=status,
            )
        )
    return db_path, asset_ids


class TestBatchEnable:
    """PATCH /api/assets/batch with status=available."""

    def test_batch_all_pass(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "烹饪翻炒", 0.92)

        client = _make_client(tmp_path)
        db_path, asset_ids = _setup_multi_asset(tmp_path)

        resp = client.patch(
            "/api/assets/batch",
            json={"asset_ids": asset_ids, "status": "available"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] == len(asset_ids)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        for aid in asset_ids:
            row = conn.execute(
                "SELECT status FROM assets WHERE asset_id = ?", (aid,)
            ).fetchone()
            assert row["status"] == "available"
        conn.close()

    def test_batch_vision_zero_confidence(self, tmp_path, monkeypatch) -> None:
        _mock_validate_vision_config_ok(monkeypatch)
        _mock_thumbnail_generate(monkeypatch)
        _mock_classify_frame(monkeypatch, "产品特写", 0.0)

        client = _make_client(tmp_path)
        db_path, asset_ids = _setup_multi_asset(tmp_path)

        resp = client.patch(
            "/api/assets/batch",
            json={"asset_ids": asset_ids, "status": "available"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "zero_confidence"

    def test_batch_vision_config_invalid(self, tmp_path, monkeypatch) -> None:
        def _raise(*a, **kw):
            raise VisionConfigError("missing api_key")

        monkeypatch.setattr(
            "apps.control_plane.routes.assets.helpers.validate_vision_config",
            _raise,
        )

        client = _make_client(tmp_path)
        db_path, asset_ids = _setup_multi_asset(tmp_path)

        resp = client.patch(
            "/api/assets/batch",
            json={"asset_ids": asset_ids, "status": "available"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "vision_config_invalid"

    def test_batch_no_reclassify_needed(self, tmp_path, monkeypatch) -> None:
        """All assets already good -> simple batch update."""
        client = _make_client(tmp_path)
        db_path, asset_ids = _setup_multi_asset(tmp_path)

        # All assets are already "available", change to "disabled"
        resp = client.patch(
            "/api/assets/batch",
            json={"asset_ids": asset_ids, "status": "disabled"},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == len(asset_ids)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        for aid in asset_ids:
            row = conn.execute(
                "SELECT status FROM assets WHERE asset_id = ?", (aid,)
            ).fetchone()
            assert row["status"] == "disabled"
        conn.close()

    def test_batch_all_good_available_no_reclassify(
        self, tmp_path, monkeypatch
    ) -> None:
        """All assets already have confidence>0 and valid category -> no reclassify."""
        client = _make_client(tmp_path)
        db_path = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        good_ids = ["good_001", "good_002"]
        for aid in good_ids:
            cat_dir = (
                tmp_path
                / "workspace"
                / "shared_assets"
                / "indexed"
                / "test-product"
                / "产品特写"
            )
            cat_dir.mkdir(parents=True, exist_ok=True)
            file_path = cat_dir / f"{aid}.mp4"
            file_path.write_bytes(b"fake mp4")
            repo = AssetRepository(db_path)
            repo.insert(
                AssetRecord(
                    asset_id=aid,
                    file_path=str(file_path.resolve()),
                    category="产品特写",
                    product="test-product",
                    confidence=0.95,
                    status="available",
                )
            )

        resp = client.patch(
            "/api/assets/batch",
            json={"asset_ids": good_ids, "status": "available"},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 2
