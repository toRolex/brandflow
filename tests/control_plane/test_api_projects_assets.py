from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.pipeline_services.asset_library import (
    AssetIndexer,
    AssetRecord,
    AssetRepository,
    Category,
)


def _make_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def _create_project_dir(tmp_path: Path, project_id: str) -> Path:
    project_dir = tmp_path / "workspace" / "projects" / project_id
    (project_dir / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
    return project_dir


def test_get_indexed_assets_requires_existing_project(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    resp = client.get("/api/projects/missing-project/assets/indexed")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "project not found"}


def test_get_indexed_assets_returns_empty_when_db_missing(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    _create_project_dir(tmp_path, "prj_assets")

    resp = client.get("/api/projects/prj_assets/assets/indexed")

    assert resp.status_code == 200
    assert resp.json() == {
        "assets": [],
        "stats": {
            "total_clips": 0,
            "available_clips": 0,
            "disabled_clips": 0,
            "source_videos": 0,
        },
    }


def test_post_index_skips_existing_source_video(tmp_path: Path, monkeypatch) -> None:
    client = _make_client(tmp_path)
    project_id = "prj_assets"
    project_dir = _create_project_dir(tmp_path, project_id)
    source_dir = project_dir / "runtime" / "source_assets"
    (source_dir / "a.mp4").write_bytes(b"a")
    (source_dir / "b.mp4").write_bytes(b"b")

    db_path = project_dir / "asset_index.db"
    repo = AssetRepository(db_path)
    repo.insert(
        AssetRecord(
            asset_id="asset_existing",
            file_path=str(
                (project_dir / "runtime" / "indexed_clips" / "x.mp4").resolve()
            ),
            category=Category.MACRO,
            product="荔枝菌",
            source_video=str((source_dir / "a.mp4").resolve()),
        )
    )

    captured: dict[str, list[str]] = {"videos": []}

    def _fake_ingest_one(self, video_path: Path, output_base: Path):
        captured["videos"].append(video_path.name)
        repo_local = self.repository
        repo_local.insert(
            AssetRecord(
                asset_id=f"asset_{video_path.stem}",
                file_path=str(
                    (
                        output_base
                        / "荔枝菌"
                        / "产品特写"
                        / f"{video_path.stem}_001.mp4"
                    ).resolve()
                ),
                category=Category.MACRO,
                product="荔枝菌",
                source_video=str(video_path.resolve()),
            )
        )
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    resp = client.post(f"/api/projects/{project_id}/assets/index")

    assert resp.status_code == 200
    assert resp.json() == {"indexed": 1, "skipped": 1, "total_clips": 2}
    assert captured["videos"] == ["b.mp4"]

    resp_again = client.post(f"/api/projects/{project_id}/assets/index")

    assert resp_again.status_code == 200
    assert resp_again.json() == {"indexed": 0, "skipped": 2, "total_clips": 2}
    assert captured["videos"] == ["b.mp4"]


def test_patch_asset_status_supports_batch(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    project_id = "prj_assets"
    project_dir = _create_project_dir(tmp_path, project_id)
    db_path = project_dir / "asset_index.db"
    repo = AssetRepository(db_path)
    for asset_id in ("asset_1", "asset_2"):
        repo.insert(
            AssetRecord(
                asset_id=asset_id,
                file_path=str((project_dir / "runtime" / f"{asset_id}.mp4").resolve()),
                category=Category.MACRO,
                product="荔枝菌",
            )
        )

    resp = client.patch(
        f"/api/projects/{project_id}/assets/batch",
        json={"status": "disabled", "asset_ids": ["asset_1", "asset_2"]},
    )

    assert resp.status_code == 200
    assert resp.json() == {"updated": 2}

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT asset_id, status FROM assets ORDER BY asset_id"
    ).fetchall()
    conn.close()
    assert rows == [("asset_1", "disabled"), ("asset_2", "disabled")]


def test_patch_asset_status_updates_single_asset(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    project_id = "prj_assets"
    project_dir = _create_project_dir(tmp_path, project_id)
    db_path = project_dir / "asset_index.db"
    repo = AssetRepository(db_path)
    repo.insert(
        AssetRecord(
            asset_id="asset_1",
            file_path=str((project_dir / "runtime" / "asset_1.mp4").resolve()),
            category=Category.MACRO,
            product="荔枝菌",
        )
    )

    resp = client.patch(
        f"/api/projects/{project_id}/assets/asset_1",
        json={"status": "disabled"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"updated": 1}


def test_patch_asset_status_batch_requires_asset_ids(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    project_id = "prj_assets"
    _create_project_dir(tmp_path, project_id)

    resp = client.patch(
        f"/api/projects/{project_id}/assets/batch",
        json={"status": "disabled"},
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "asset_ids must be a non-empty string array"}


def test_patch_asset_status_batch_rejects_non_string_array(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    project_id = "prj_assets"
    _create_project_dir(tmp_path, project_id)

    resp = client.patch(
        f"/api/projects/{project_id}/assets/batch",
        json={"status": "disabled", "asset_ids": "asset_1"},
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "asset_ids must be a non-empty string array"}


def test_patch_asset_status_rejects_non_object_payload(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    project_id = "prj_assets"
    _create_project_dir(tmp_path, project_id)

    resp = client.patch(
        f"/api/projects/{project_id}/assets/asset_1",
        json=[{"status": "disabled"}],
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "request body must be object"}


# ── Issue #96: resolve_vision_config + category_names wiring ──


def test_project_index_uses_resolve_vision_config(tmp_path: Path, monkeypatch) -> None:
    """POST /api/projects/{id}/assets/index 应使用 resolve_vision_config() + category_names。"""
    from apps.control_plane.routes import api_projects as ap_mod

    client = _make_client(tmp_path)
    project_id = "prj_vision"
    _create_project_dir(tmp_path, project_id)
    source_dir = (
        tmp_path / "workspace" / "projects" / project_id / "runtime" / "source_assets"
    )
    (source_dir / "test.mp4").write_bytes(b"fake video data")

    resolve_called: list[bool] = []
    category_names_captured: list[list[str] | None] = []

    def _fake_resolve(providers_payload, secrets=None, reader=None):
        resolve_called.append(True)
        return {
            "provider": "xiaomi",
            "api_key": "test-key",
            "endpoint": "https://test.com",
            "model": "test-model",
        }

    def _fake_init(
        self,
        ffmpeg_path,
        repository,
        vision_config=None,
        product="",
        category_names=None,
    ):
        category_names_captured.append(category_names)
        self.ffmpeg_path = ffmpeg_path
        self.repository = repository
        self.vision_config = vision_config or {}
        self.product = product
        self.category_names = category_names

    monkeypatch.setattr(ap_mod, "resolve_vision_config", _fake_resolve)
    monkeypatch.setattr(AssetIndexer, "__init__", _fake_init)
    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        lambda self, video_path, output_base, log_callback=None: [],
    )

    resp = client.post(f"/api/projects/{project_id}/assets/index")

    assert resp.status_code == 200
    assert len(resolve_called) == 1, (
        "应调用 resolve_vision_config() 而非 get_vision_config()"
    )
    assert len(category_names_captured) == 1
    assert category_names_captured[0] is not None, "应传入 category_names"
    assert len(category_names_captured[0]) > 0, "category_names 不应为空"


def test_project_index_product_fallback(tmp_path: Path, monkeypatch) -> None:
    """meta.product 为空时回退到 reader.get_product_config() 的 name -> default_name -> id 链。"""
    client = _make_client(tmp_path)
    project_id = "prj_fallback"
    _create_project_dir(tmp_path, project_id)
    source_dir = (
        tmp_path / "workspace" / "projects" / project_id / "runtime" / "source_assets"
    )
    (source_dir / "test.mp4").write_bytes(b"fake video data")

    captured_product: list[str] = []

    def _fake_init(
        self,
        ffmpeg_path,
        repository,
        vision_config=None,
        product="",
        category_names=None,
    ):
        captured_product.append(product)
        self.ffmpeg_path = ffmpeg_path
        self.repository = repository
        self.vision_config = vision_config or {}
        self.product = product
        self.category_names = category_names

    def _fake_get_product_config(self, product_id=None):
        return {"name": "", "default_name": "默认产品", "id": "fallback-id"}

    monkeypatch.setattr(
        "packages.provider_config.config_reader.ConfigReader.get_product_config",
        _fake_get_product_config,
    )
    monkeypatch.setattr(AssetIndexer, "__init__", _fake_init)
    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        lambda self, video_path, output_base, log_callback=None: [],
    )

    resp = client.post(f"/api/projects/{project_id}/assets/index")

    assert resp.status_code == 200
    assert len(captured_product) == 1
    # meta.product is empty, should fall back to reader.get_product_config() -> default_name
    assert captured_product[0] == "默认产品", (
        f"应回退到 default_name='默认产品'，实际: {captured_product[0]}"
    )
