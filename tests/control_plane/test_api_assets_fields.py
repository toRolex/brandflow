"""Tests for asset field update endpoints — category validation.

Covers #73: single and batch asset field updates must validate the submitted
category against the configured (product / instance / default) category list.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.pipeline_services.asset_library import (
    AssetRecord,
    AssetRepository,
    Category,
)


def _make_client(tmp_path: Path) -> TestClient:
    """Create a FastAPI TestClient rooted at *tmp_path*."""
    return TestClient(create_app(tmp_path))


def _write_config(root_dir: Path, config: dict) -> None:
    """Write app_config.json at <root_dir>/config/ for ConfigReader."""
    config_dir = root_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "app_config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )


def _setup_asset_db(root_dir: Path) -> tuple[Path, str, str, str]:
    """Create the shared asset DB with one indexed asset and a file on disk.

    Returns (db_path, asset_id, old_category, old_product, old_file_path).
    """
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    indexed_dir = root_dir / "workspace" / "shared_assets" / "indexed" / "荔枝菌" / "产品特写"
    indexed_dir.mkdir(parents=True, exist_ok=True)
    file_path = indexed_dir / "test_clip_001.mp4"
    file_path.write_bytes(b"fake mp4 content")

    repo = AssetRepository(db_path)
    asset_id = "asset_test_001"
    repo.insert(
        AssetRecord(
            asset_id=asset_id,
            file_path=str(file_path.resolve()),
            category=Category.MACRO.value,
            product="荔枝菌",
        )
    )
    return db_path, asset_id, Category.MACRO.value, "荔枝菌", str(file_path.resolve())


# ── Single asset field update (PATCH /api/assets/{asset_id}/fields) ──


def test_patch_asset_fields_valid_custom_category(tmp_path: Path) -> None:
    """Custom product category should be accepted when configured."""
    _write_config(
        tmp_path,
        {"product": {"categories": [
            {"id": "promo", "name": "促销活动"},
            {"id": "unboxing", "name": "开箱展示"},
        ]}},
    )

    client = _make_client(tmp_path)
    db_path, asset_id, old_cat, old_product, old_file = _setup_asset_db(tmp_path)

    resp = client.patch(
        f"/api/assets/{asset_id}/fields",
        json={"category": "促销活动"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"updated": 1}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT category, product FROM assets WHERE asset_id = ?", (asset_id,)
    ).fetchone()
    conn.close()
    assert row["category"] == "促销活动"
    assert row["product"] == old_product


def test_patch_asset_fields_valid_old_food_category(tmp_path: Path) -> None:
    """Old default food categories should still be accepted (backward compat)."""
    client = _make_client(tmp_path)
    db_path, asset_id, old_cat, old_product, old_file = _setup_asset_db(tmp_path)

    resp = client.patch(
        f"/api/assets/{asset_id}/fields",
        json={"category": "烹饪翻炒"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"updated": 1}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT category FROM assets WHERE asset_id = ?", (asset_id,)
    ).fetchone()
    conn.close()
    assert row["category"] == "烹饪翻炒"


def test_patch_asset_fields_invalid_category_returns_error(tmp_path: Path) -> None:
    """An unrecognized category should return a 400 error."""
    client = _make_client(tmp_path)
    db_path, asset_id, old_cat, old_product, old_file = _setup_asset_db(tmp_path)

    resp = client.patch(
        f"/api/assets/{asset_id}/fields",
        json={"category": "不存在的分类"},
    )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "不存在的分类" in detail
    assert "分类" in detail

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT category FROM assets WHERE asset_id = ?", (asset_id,)
    ).fetchone()
    conn.close()
    assert row["category"] == old_cat


def test_patch_asset_fields_file_move_on_category_change(tmp_path: Path) -> None:
    """When category changes, the file should be moved to the new directory."""
    _write_config(
        tmp_path,
        {"product": {"categories": [{"id": "promo", "name": "促销活动"}]}},
    )

    client = _make_client(tmp_path)
    db_path, asset_id, old_cat, old_product, old_file = _setup_asset_db(tmp_path)

    resp = client.patch(
        f"/api/assets/{asset_id}/fields",
        json={"category": "促销活动"},
    )

    assert resp.status_code == 200

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT file_path FROM assets WHERE asset_id = ?", (asset_id,)
    ).fetchone()
    conn.close()

    new_path = Path(row["file_path"])
    assert "促销活动" in str(new_path)
    assert new_path.exists()
    assert not Path(old_file).exists()


def test_patch_asset_fields_no_category_change_keeps_file(tmp_path: Path) -> None:
    """Updating only product (not category) should keep the file in place."""
    client = _make_client(tmp_path)
    db_path, asset_id, old_cat, old_product, old_file = _setup_asset_db(tmp_path)

    resp = client.patch(
        f"/api/assets/{asset_id}/fields",
        json={"product": "羊肚菌"},
    )

    assert resp.status_code == 200
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT product, category, file_path FROM assets WHERE asset_id = ?",
        (asset_id,),
    ).fetchone()
    conn.close()
    assert row["product"] == "羊肚菌"
    assert row["category"] == old_cat
    # File moved to new product dir
    new_path_prod = Path(row["file_path"])
    assert "羊肚菌" in str(new_path_prod)
    assert new_path_prod.exists()


# ── Batch asset field update (PATCH /api/assets/batch-fields) ──


def _setup_multi_asset_db(root_dir: Path) -> tuple[Path, list[str], str, list[str]]:
    """Create two assets for batch testing."""
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    asset_ids = []
    file_paths = []
    for i in range(2):
        idx = i + 1
        cat_dir = root_dir / "workspace" / "shared_assets" / "indexed" / "荔枝菌" / "产品特写"
        cat_dir.mkdir(parents=True, exist_ok=True)
        file_path = cat_dir / f"test_clip_{idx:03d}.mp4"
        file_path.write_bytes(b"fake mp4 batch")
        asset_ids.append(f"asset_batch_{idx:03d}")
        file_paths.append(str(file_path.resolve()))

    repo = AssetRepository(db_path)
    for aid, fp in zip(asset_ids, file_paths):
        repo.insert(
            AssetRecord(
                asset_id=aid,
                file_path=fp,
                category=Category.MACRO.value,
                product="荔枝菌",
            )
        )
    return db_path, asset_ids, Category.MACRO.value, file_paths


def test_batch_fields_valid_custom_category(tmp_path: Path) -> None:
    """Batch update with a custom product category should succeed."""
    _write_config(
        tmp_path,
        {"product": {"categories": [{"id": "promo", "name": "促销活动"}]}},
    )

    client = _make_client(tmp_path)
    db_path, asset_ids, old_cat, file_paths = _setup_multi_asset_db(tmp_path)

    resp = client.patch(
        "/api/assets/batch-fields",
        json={"asset_ids": asset_ids, "category": "促销活动"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"updated": 2}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT asset_id, category FROM assets ORDER BY asset_id"
    ).fetchall()
    conn.close()
    for row in rows:
        assert row["category"] == "促销活动"


def test_batch_fields_invalid_category_returns_error(tmp_path: Path) -> None:
    """Batch update with an invalid category should return 400 and not update."""
    client = _make_client(tmp_path)
    db_path, asset_ids, old_cat, file_paths = _setup_multi_asset_db(tmp_path)

    resp = client.patch(
        "/api/assets/batch-fields",
        json={"asset_ids": asset_ids, "category": "无效分类名"},
    )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "无效分类名" in detail

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT category FROM assets ORDER BY asset_id"
    ).fetchall()
    conn.close()
    for row in rows:
        assert row["category"] == old_cat


def test_batch_fields_old_food_category_still_valid(tmp_path: Path) -> None:
    """Old default food categories pass validation when no product custom config."""
    client = _make_client(tmp_path)
    db_path, asset_ids, old_cat, file_paths = _setup_multi_asset_db(tmp_path)

    resp = client.patch(
        "/api/assets/batch-fields",
        json={"asset_ids": asset_ids, "category": "烹饪翻炒"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"updated": 2}


def test_batch_fields_file_move_consistency(tmp_path: Path) -> None:
    """Files should move to the new category directory on batch category change."""
    _write_config(
        tmp_path,
        {"product": {"categories": [{"id": "unboxing", "name": "开箱展示"}]}},
    )

    client = _make_client(tmp_path)
    db_path, asset_ids, old_cat, file_paths = _setup_multi_asset_db(tmp_path)

    resp = client.patch(
        "/api/assets/batch-fields",
        json={"asset_ids": asset_ids, "category": "开箱展示"},
    )

    assert resp.status_code == 200

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT file_path FROM assets ORDER BY asset_id"
    ).fetchall()
    conn.close()

    for row in rows:
        fp = Path(row["file_path"])
        assert "开箱展示" in str(fp)
        assert fp.exists()

    for old_fp in file_paths:
        assert not Path(old_fp).exists()


# ── GET /api/assets/categories endpoint tests ──


class TestGetCategoriesEndpoint:
    """GET /api/assets/categories — priority chain: product-level → instance-level → defaults."""

    def test_product_level_categories_returned(self, tmp_path: Path) -> None:
        """产品级 categories 应优先返回。"""
        _write_config(
            tmp_path,
            {
                "products": [
                    {
                        "id": "prod-a",
                        "name": "产品A",
                        "categories": [
                            {"id": "unboxing", "name": "开箱展示", "description": "开箱"},
                            {"id": "tasting", "name": "试吃品尝", "description": "试吃"},
                        ],
                    },
                ],
                "active_product_id": "prod-a",
                "asset_library": {
                    "categories": [
                        {"id": "origin", "name": "产地溯源", "description": "产地"},
                    ],
                },
            },
        )
        client = _make_client(tmp_path)
        resp = client.get("/api/assets/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "unboxing"
        assert data[0]["name"] == "开箱展示"
        assert data[0]["description"] == "开箱"
        assert data[1]["id"] == "tasting"

    def test_fallback_to_instance_level(self, tmp_path: Path) -> None:
        """产品未配置 categories 时回退到 asset_library.categories。"""
        _write_config(
            tmp_path,
            {
                "products": [
                    {"id": "prod-b"},
                ],
                "active_product_id": "prod-b",
                "asset_library": {
                    "categories": [
                        {"id": "origin", "name": "产地溯源", "description": "原产地"},
                        {"id": "sorting", "name": "筛选分拣", "description": "分拣"},
                    ],
                },
            },
        )
        client = _make_client(tmp_path)
        resp = client.get("/api/assets/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "origin"
        assert data[1]["id"] == "sorting"

    def test_fallback_to_defaults(self, tmp_path: Path) -> None:
        """产品和 asset_library 均未配置 categories 时返回默认分类。"""
        _write_config(
            tmp_path,
            {
                "products": [
                    {"id": "prod-c"},
                ],
                "active_product_id": "prod-c",
            },
        )
        client = _make_client(tmp_path)
        resp = client.get("/api/assets/categories")
        assert resp.status_code == 200
        data = resp.json()
        # 默认 food categories 有 10 个
        assert len(data) == 10
        default_ids = [c["id"] for c in data]
        assert "origin" in default_ids
        assert "stir_fry" in default_ids
        assert "finished" in default_ids

    def test_empty_product_categories_falls_to_instance(self, tmp_path: Path) -> None:
        """产品显式设置空 categories 列表时回退到 asset_library。"""
        _write_config(
            tmp_path,
            {
                "products": [
                    {"id": "prod-d", "categories": []},
                ],
                "active_product_id": "prod-d",
                "asset_library": {
                    "categories": [
                        {"id": "macro", "name": "产品特写", "description": "特写"},
                    ],
                },
            },
        )
        client = _make_client(tmp_path)
        resp = client.get("/api/assets/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "macro"

    def test_both_empty_returns_defaults(self, tmp_path: Path) -> None:
        """产品和 asset_library 均为空 categories 时返回默认分类。"""
        _write_config(
            tmp_path,
            {
                "products": [
                    {"id": "prod-e", "categories": []},
                ],
                "active_product_id": "prod-e",
                "asset_library": {"categories": []},
            },
        )
        client = _make_client(tmp_path)
        resp = client.get("/api/assets/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 10  # 默认 food categories
