"""Test POST /api/assets/index product resolution (issue #58)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.pipeline_services.asset_library.models import AssetRecord


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def _setup_source_videos(tmp_path: Path) -> Path:
    source_dir = tmp_path / "workspace" / "shared_assets" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "test.mp4").write_bytes(b"fake video data")
    return source_dir


def test_index_uses_explicit_product_param(tmp_path: Path, monkeypatch) -> None:
    """参数显式传入 product="零食测试" 时，AssetIndexer 使用该值。"""
    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    captured_product: list[str] = []

    def _fake_ingest_one(self, video_path: Path, output_base: Path, log_callback=None):
        captured_product.append(self.product)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False, "product": "零食测试"})

    assert resp.status_code == 200
    assert captured_product == ["零食测试"]


def test_index_falls_back_to_active_product(tmp_path: Path, monkeypatch) -> None:
    """未传 product 时，从 ConfigReader 活跃产品名读取。"""
    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    captured_product: list[str] = []

    def _fake_ingest_one(self, video_path: Path, output_base: Path, log_callback=None):
        captured_product.append(self.product)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    # Mock ConfigReader.get_product_config to return active product with name
    def _fake_get_product_config(self, product_id=None):
        return {"name": "测试产品", "id": "test-product", "default_name": "测试产品"}

    monkeypatch.setattr(
        "packages.provider_config.app_config.AppConfigManager.get_product_config",
        _fake_get_product_config,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 200
    assert captured_product == ["测试产品"]


def test_index_explicit_product_wins_over_config(tmp_path: Path, monkeypatch) -> None:
    """显式传入 product 时，忽略 ConfigReader 的值。"""
    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    captured_product: list[str] = []

    def _fake_ingest_one(self, video_path: Path, output_base: Path, log_callback=None):
        captured_product.append(self.product)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    def _fake_get_product_config(self, product_id=None):
        return {"name": "配置中的产品", "id": "config-product"}

    monkeypatch.setattr(
        "packages.provider_config.app_config.AppConfigManager.get_product_config",
        _fake_get_product_config,
    )

    resp = client.post(
        "/api/assets/index",
        params={"async_mode": False, "product": "显式传入"},
    )

    assert resp.status_code == 200
    assert captured_product == ["显式传入"]


def test_indexed_asset_has_non_empty_product(tmp_path: Path, monkeypatch) -> None:
    """索引后的素材 product 字段非空，可被 AssetRetriever 匹配。"""
    from packages.pipeline_services.asset_library.repository import AssetRepository
    from packages.file_store.paths import shared_asset_db_path

    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    def _fake_ingest_one(self, video_path: Path, output_base: Path, log_callback=None):
        from datetime import datetime, timezone

        repo = self.repository
        now = datetime.now(timezone.utc).isoformat()
        record = AssetRecord(
            asset_id="asset_test_001",
            file_path=str(output_base / self.product / "产品特写" / "test_001.mp4"),
            category="产品特写",
            product=self.product,
            confidence=0.85,
            source_video=str(video_path.resolve()),
            created_at=now,
        )
        repo.insert(record)
        return [record]

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    resp = client.post(
        "/api/assets/index",
        params={"async_mode": False, "product": "零食测试"},
    )

    assert resp.status_code == 200
    assert resp.json()["indexed"] == 1

    # 验证 DB 中素材 product 字段为 "零食测试"
    db_path = shared_asset_db_path(tmp_path)
    repo = AssetRepository(db_path)
    results = repo.query_all_available("零食测试")
    assert len(results) == 1
    assert results[0].product == "零食测试"

    # 验证用错误 product 查不到
    empty = repo.query_all_available("其他产品")
    assert len(empty) == 0


def test_index_uses_resolve_product_name(tmp_path: Path, monkeypatch) -> None:
    """api_assets 应使用 resolve_product_name 做产品名解析。"""
    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    captured_product: list[str] = []

    def _fake_ingest_one(self, video_path: Path, output_base: Path, log_callback=None):
        captured_product.append(self.product)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    def _fake_resolve_name(self, explicit_product=""):
        if explicit_product:
            return explicit_product
        return "零食测试"

    monkeypatch.setattr(
        "packages.provider_config.app_config.AppConfigManager.resolve_product_name",
        _fake_resolve_name,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 200
    assert captured_product == ["零食测试"]


def test_index_falls_back_to_default_name(tmp_path: Path, monkeypatch) -> None:
    """name 为空但 default_name 有值时，素材入库应使用 default_name。"""
    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    captured_product: list[str] = []

    def _fake_ingest_one(self, video_path: Path, output_base: Path, log_callback=None):
        captured_product.append(self.product)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    # Simulate: name="" default_name="零食测试"
    def _fake_get_product_config(self, product_id=None):
        return {"name": "", "default_name": "零食测试", "id": "snack"}

    monkeypatch.setattr(
        "packages.provider_config.app_config.AppConfigManager.get_product_config",
        _fake_get_product_config,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 200
    assert captured_product == ["零食测试"]


def test_index_falls_back_to_id(tmp_path: Path, monkeypatch) -> None:
    """name 和 default_name 都为空时，素材入库应使用 product id。"""
    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    captured_product: list[str] = []

    def _fake_ingest_one(self, video_path: Path, output_base: Path, log_callback=None):
        captured_product.append(self.product)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    def _fake_get_product_config(self, product_id=None):
        return {"name": "", "default_name": "", "id": "snack-prod"}

    monkeypatch.setattr(
        "packages.provider_config.app_config.AppConfigManager.get_product_config",
        _fake_get_product_config,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 200
    assert captured_product == ["snack-prod"]
