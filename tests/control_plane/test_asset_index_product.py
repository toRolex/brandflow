"""Test POST /api/assets/index product resolution (issue #58) and vision config wiring (issue #96)."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.pipeline_services.asset_library import AssetIndexer
from packages.pipeline_services.asset_library.models import AssetRecord


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def _setup_source_videos(tmp_path: Path) -> Path:
    source_dir = tmp_path / "workspace" / "shared_assets" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "test.mp4").write_bytes(b"fake video data")
    return source_dir


def _mock_vision_config_ok(monkeypatch) -> None:
    """Make validate_vision_config a no-op so product-resolution tests can focus."""
    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.validate_vision_config",
        lambda *a, **kw: None,
    )


def test_index_uses_explicit_product_param(tmp_path: Path, monkeypatch) -> None:
    """参数显式传入 product="零食测试" 时，AssetIndexer 使用该值。"""
    _mock_vision_config_ok(monkeypatch)
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

    resp = client.post(
        "/api/assets/index", params={"async_mode": False, "product": "零食测试"}
    )

    assert resp.status_code == 200
    assert captured_product == ["零食测试"]


def test_index_falls_back_to_active_product(tmp_path: Path, monkeypatch) -> None:
    """未传 product 时，从 ConfigReader 活跃产品名读取。"""
    _mock_vision_config_ok(monkeypatch)
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
        "packages.provider_config.config_reader.ConfigReader.get_product_config",
        _fake_get_product_config,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 200
    assert captured_product == ["测试产品"]


def test_index_explicit_product_wins_over_config(tmp_path: Path, monkeypatch) -> None:
    """显式传入 product 时，忽略 ConfigReader 的值。"""
    _mock_vision_config_ok(monkeypatch)
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
        "packages.provider_config.config_reader.ConfigReader.get_product_config",
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
    _mock_vision_config_ok(monkeypatch)
    from packages.pipeline_services.asset_library.repository import AssetRepository

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
    db_path = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
    repo = AssetRepository(db_path)
    results = repo.query_all_available("零食测试")
    assert len(results) == 1
    assert results[0].product == "零食测试"

    # 验证用错误 product 查不到
    empty = repo.query_all_available("其他产品")
    assert len(empty) == 0


def test_index_uses_resolve_product_name(tmp_path: Path, monkeypatch) -> None:
    """api_assets 应使用 resolve_product_name 做产品名解析。"""
    _mock_vision_config_ok(monkeypatch)
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
        "apps.control_plane.routes.api_assets._resolve_product_name",
        _fake_resolve_name,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 200
    assert captured_product == ["零食测试"]


def test_index_falls_back_to_default_name(tmp_path: Path, monkeypatch) -> None:
    """name 为空但 default_name 有值时，素材入库应使用 default_name。"""
    _mock_vision_config_ok(monkeypatch)
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
        "packages.provider_config.config_reader.ConfigReader.get_product_config",
        _fake_get_product_config,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 200
    assert captured_product == ["零食测试"]


def test_index_falls_back_to_id(tmp_path: Path, monkeypatch) -> None:
    """name 和 default_name 都为空时，素材入库应使用 product id。"""
    _mock_vision_config_ok(monkeypatch)
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
        "packages.provider_config.config_reader.ConfigReader.get_product_config",
        _fake_get_product_config,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 200
    assert captured_product == ["snack-prod"]


# ── Issue #96: resolve_vision_config + category_names wiring ──


def test_sync_index_uses_resolve_vision_config(tmp_path: Path, monkeypatch) -> None:
    """同步路径应调用 resolve_vision_config()，传入 category_names 给 AssetIndexer。"""
    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    resolve_called: list[dict] = []
    category_names_captured: list[list[str] | None] = []

    def _fake_resolve(providers_payload, secrets=None, reader=None):
        resolve_called.append({"secrets": secrets, "reader": reader})
        return {
            "provider": "xiaomi",
            "api_key": "test-vision-key",
            "endpoint": "https://test.api.com",
            "model": "test-vision-model",
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

    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.resolve_vision_config",
        _fake_resolve,
    )
    monkeypatch.setattr(AssetIndexer, "__init__", _fake_init)
    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        lambda self, video_path, output_base, log_callback=None: [],
    )
    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.validate_vision_config",
        lambda *a, **kw: None,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 200
    assert len(resolve_called) == 1, (
        "应调用 resolve_vision_config() 而非 get_vision_config()"
    )
    assert resolve_called[0]["reader"] is not None, "应传入 ConfigReader"
    assert len(category_names_captured) == 1
    assert category_names_captured[0] is not None, "应传入 category_names"
    assert len(category_names_captured[0]) > 0, "category_names 不应为空"


def test_async_index_uses_resolve_vision_config(tmp_path: Path, monkeypatch) -> None:
    """异步路径 _run_index_task 应调用 resolve_vision_config() 并传入 category_names。"""
    import asyncio

    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    resolve_called: list[bool] = []
    category_names_captured: list[list[str] | None] = []

    def _fake_resolve(providers_payload, secrets=None, reader=None):
        resolve_called.append(True)
        return {
            "provider": "xiaomi",
            "api_key": "test-vision-key",
            "endpoint": "https://test.api.com",
            "model": "test-vision-model",
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

    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.resolve_vision_config",
        _fake_resolve,
    )
    monkeypatch.setattr(AssetIndexer, "__init__", _fake_init)
    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        lambda self, video_path, output_base, log_callback=None: [],
    )
    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.validate_vision_config",
        lambda *a, **kw: None,
    )

    resp = client.post("/api/assets/index", params={"async_mode": True})

    assert resp.status_code == 200
    assert "task_id" in resp.json()

    # 等待后台异步任务完成（_ingest_one_video 被 mock 为 no-op，会很快）
    asyncio.run(asyncio.sleep(0.2))

    assert len(resolve_called) > 0, "异步路径应调用 resolve_vision_config()"
    assert len(category_names_captured) > 0, (
        "异步路径应向 AssetIndexer 传入 category_names"
    )
    assert category_names_captured[0] is not None
    assert len(category_names_captured[0]) > 0, "category_names 不应为空"


# ── Issue #123: Vision 配置校验 ────────────────────────────────────────────


def test_sync_index_fails_on_invalid_vision_config(tmp_path, monkeypatch):
    """同步路径：Vision api_key 已设但其他字段缺失时索引任务应失败。"""
    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    def _fake_resolve(providers_payload, secrets=None, reader=None):
        return {
            "provider": "xiaomi",
            "api_key": "sk-test",  # 有 api_key 说明 Vision 被显式配置
            "endpoint": "",  # 但 endpoint 缺失 = 配置不完整
            "model": "",
        }

    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.resolve_vision_config",
        _fake_resolve,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 422, (
        f"Vision 配置无效时应返回 422，实际: {resp.status_code}, body: {resp.text}"
    )
    data = resp.json()
    assert data["detail"]["code"] == "vision_config_invalid", (
        f"响应应包含 detail.code=vision_config_invalid，实际: {data}"
    )
    assert "Vision" in resp.text, f"响应应包含 Vision 错误信息，实际: {resp.text}"


def test_async_index_task_fails_on_invalid_vision_config(tmp_path, monkeypatch):
    """异步路径：Vision api_key 已设但其他字段缺失时后台任务应标记为 FAILED。"""
    import asyncio

    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    def _fake_resolve(providers_payload, secrets=None, reader=None):
        return {
            "provider": "xiaomi",
            "api_key": "sk-test",  # 有 api_key 说明 Vision 被显式配置
            "endpoint": "",  # 但 endpoint 缺失 = 配置不完整
            "model": "",
        }

    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.resolve_vision_config",
        _fake_resolve,
    )

    resp = client.post("/api/assets/index", params={"async_mode": True})

    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # 等待后台任务执行完毕
    asyncio.run(asyncio.sleep(0.3))

    # 检查任务状态
    status_resp = client.get(f"/api/assets/index/{task_id}/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "failed", (
        f"无效 Vision 配置时任务应失败，实际 status: {data['status']}, error: {data.get('error')}"
    )
    assert "Vision" in data.get("error", ""), (
        f"错误信息应包含 Vision 相关描述，实际: {data.get('error')}"
    )


def test_sync_index_fails_when_vision_not_configured(tmp_path, monkeypatch):
    """同步路径：Vision 完全未配置时索引任务应直接 422。"""
    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    def _fake_resolve(providers_payload, secrets=None, reader=None):
        return {
            "provider": "",
            "api_key": "",
            "endpoint": "",
            "model": "",
        }

    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.resolve_vision_config",
        _fake_resolve,
    )

    resp = client.post("/api/assets/index", params={"async_mode": False})

    assert resp.status_code == 422, (
        f"Vision 未配置时应返回 422，实际: {resp.status_code}, body: {resp.text}"
    )
    data = resp.json()
    assert data["detail"]["code"] == "vision_config_invalid", (
        f"响应应包含 detail.code=vision_config_invalid，实际: {data}"
    )


def test_async_index_fails_when_vision_not_configured(tmp_path, monkeypatch):
    """异步路径：Vision 完全未配置时后台任务应标记为 FAILED。"""
    import asyncio

    client = _client(tmp_path)
    _setup_source_videos(tmp_path)

    def _fake_resolve(providers_payload, secrets=None, reader=None):
        return {
            "provider": "",
            "api_key": "",
            "endpoint": "",
            "model": "",
        }

    monkeypatch.setattr(
        "apps.control_plane.routes.api_assets.resolve_vision_config",
        _fake_resolve,
    )

    resp = client.post("/api/assets/index", params={"async_mode": True})

    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    asyncio.run(asyncio.sleep(0.3))

    status_resp = client.get(f"/api/assets/index/{task_id}/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "failed", (
        f"Vision 未配置时任务应失败，实际 status: {data['status']}, error: {data.get('error')}"
    )
    assert "Vision" in data.get("error", ""), (
        f"错误信息应包含 Vision 相关描述，实际: {data.get('error')}"
    )


# ── Issue #139: 批量重分类未映射素材 ─────────────────────────────────────────


def test_batch_update_categories(tmp_path: Path) -> None:
    """PATCH /api/assets/categories 批量更新素材分类。"""
    from packages.pipeline_services.asset_library.repository import AssetRepository

    client = _client(tmp_path)

    # Insert test assets into the DB
    db_path = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    AssetRepository(db_path)  # Initialize tables

    conn = sqlite3.connect(str(db_path))
    now = "2025-01-01T00:00:00"
    test_assets = [
        (
            "a1",
            "/path/to/a1.mp4",
            "旧分类",
            "龙井茶",
            0.9,
            5.0,
            "available",
            0,
            "v1.mp4",
        ),
        (
            "a2",
            "/path/to/a2.mp4",
            "旧分类",
            "龙井茶",
            0.85,
            3.0,
            "available",
            0,
            "v1.mp4",
        ),
        ("a3", "/path/to/a3.mp4", "冲泡", "龙井茶", 0.8, 7.0, "available", 0, "v2.mp4"),
    ]
    for asset in test_assets:
        conn.execute(
            """INSERT INTO assets
               (asset_id, file_path, category, product, confidence, duration_seconds,
                status, usage_count, source_video, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (*asset, now, now),
        )
    conn.commit()
    conn.close()

    # Call the endpoint
    resp = client.patch(
        "/api/assets/categories",
        json={"asset_ids": ["a1", "a2"], "category": "产品特写"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"updated": 2}

    # Verify in DB
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT asset_id, category FROM assets ORDER BY asset_id"
    ).fetchall()
    conn.close()
    assert dict(rows) == {"a1": "产品特写", "a2": "产品特写", "a3": "冲泡"}


def test_batch_update_categories_idempotent(tmp_path: Path) -> None:
    """相同请求重复执行返回相同 updated 计数。"""
    from packages.pipeline_services.asset_library.repository import AssetRepository

    client = _client(tmp_path)
    db_path = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    AssetRepository(db_path)

    conn = sqlite3.connect(str(db_path))
    now = "2025-01-01T00:00:00"
    conn.execute(
        """INSERT INTO assets
           (asset_id, file_path, category, product, confidence, duration_seconds,
            status, usage_count, source_video, tags, created_at, last_used_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "a1",
            "/p.mp4",
            "旧分类",
            "测试",
            0.9,
            5.0,
            "available",
            0,
            "v.mp4",
            "[]",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()

    # First call
    resp1 = client.patch(
        "/api/assets/categories",
        json={"asset_ids": ["a1"], "category": "新分类"},
    )
    assert resp1.status_code == 200
    assert resp1.json() == {"updated": 1}

    # Second call — same request, same result
    resp2 = client.patch(
        "/api/assets/categories",
        json={"asset_ids": ["a1"], "category": "新分类"},
    )
    assert resp2.status_code == 200
    assert resp2.json() == {"updated": 1}


def test_batch_update_categories_ignores_nonexistent(tmp_path: Path) -> None:
    """不存在的 asset_id 被静默忽略。"""
    from packages.pipeline_services.asset_library.repository import AssetRepository

    client = _client(tmp_path)
    db_path = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    AssetRepository(db_path)

    conn = sqlite3.connect(str(db_path))
    now = "2025-01-01T00:00:00"
    conn.execute(
        """INSERT INTO assets
           (asset_id, file_path, category, product, confidence, duration_seconds,
            status, usage_count, source_video, tags, created_at, last_used_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "a1",
            "/p.mp4",
            "旧分类",
            "测试",
            0.9,
            5.0,
            "available",
            0,
            "v.mp4",
            "[]",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()

    resp = client.patch(
        "/api/assets/categories",
        json={"asset_ids": ["a1", "nonexistent"], "category": "新分类"},
    )
    assert resp.status_code == 200
    # a1 is updated, nonexistent is silently skipped
    assert resp.json() == {"updated": 1}


def test_batch_update_categories_validates_asset_ids(tmp_path: Path) -> None:
    """asset_ids 为空或非法时返回 400。"""
    client = _client(tmp_path)

    resp = client.patch(
        "/api/assets/categories",
        json={"asset_ids": [], "category": "产品特写"},
    )
    assert resp.status_code == 400

    resp = client.patch(
        "/api/assets/categories",
        json={"asset_ids": "not_a_list", "category": "产品特写"},
    )
    assert resp.status_code == 400


def test_batch_update_categories_validates_category(tmp_path: Path) -> None:
    """category 为空时返回 400。"""
    client = _client(tmp_path)

    resp = client.patch(
        "/api/assets/categories",
        json={"asset_ids": ["a1"], "category": ""},
    )
    assert resp.status_code == 400

    resp = client.patch(
        "/api/assets/categories",
        json={"asset_ids": ["a1"]},  # missing category
    )
    assert resp.status_code == 400
