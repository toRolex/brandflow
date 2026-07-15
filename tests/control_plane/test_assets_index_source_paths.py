"""Test POST /api/assets/index source_paths filtering (Issue #144).

source_paths 限制索引范围为指定文件，不传时保持全目录扫描。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def test_index_respects_source_paths(tmp_path: Path, monkeypatch) -> None:
    """source_paths 只索引指定文件，不索引其他文件。"""
    client = _client(tmp_path)
    source_dir = tmp_path / "workspace" / "shared_assets" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "a.mp4").write_bytes(b"a")
    (source_dir / "b.mp4").write_bytes(b"b")
    (source_dir / "c.mp4").write_bytes(b"c")

    captured_videos: list[str] = []

    def _fake_ingest_one(self, video_path, output_base, log_callback=None):
        captured_videos.append(video_path.name)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    resp = client.post(
        "/api/assets/index",
        params={"async_mode": False},
        json={"source_paths": ["a.mp4", "c.mp4"]},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["indexed"] == 2
    assert data["skipped"] == 0
    assert set(captured_videos) == {"a.mp4", "c.mp4"}


def test_index_without_source_paths_indexes_all(tmp_path: Path, monkeypatch) -> None:
    """不传 source_paths 时，全目录扫描（向后兼容）。"""
    client = _client(tmp_path)
    source_dir = tmp_path / "workspace" / "shared_assets" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "a.mp4").write_bytes(b"a")
    (source_dir / "b.mp4").write_bytes(b"b")

    captured_videos: list[str] = []

    def _fake_ingest_one(self, video_path, output_base, log_callback=None):
        captured_videos.append(video_path.name)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    resp = client.post(
        "/api/assets/index",
        params={"async_mode": False},
    )

    assert resp.status_code == 200
    assert len(captured_videos) == 2
    assert set(captured_videos) == {"a.mp4", "b.mp4"}


def test_index_source_paths_skips_nonexistent(tmp_path: Path, monkeypatch) -> None:
    """source_paths 包含不存在的文件时只索引已存在的。"""
    client = _client(tmp_path)
    source_dir = tmp_path / "workspace" / "shared_assets" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "a.mp4").write_bytes(b"a")

    captured_videos: list[str] = []

    def _fake_ingest_one(self, video_path, output_base, log_callback=None):
        captured_videos.append(video_path.name)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    resp = client.post(
        "/api/assets/index",
        params={"async_mode": False},
        json={"source_paths": ["a.mp4", "nonexistent.mp4"]},
    )

    assert resp.status_code == 200
    assert captured_videos == ["a.mp4"]
    assert resp.json()["indexed"] == 1


def test_index_source_paths_empty_produces_no_videos(
    tmp_path: Path, monkeypatch
) -> None:
    """source_paths 为空列表时，不索引任何文件。"""
    client = _client(tmp_path)
    source_dir = tmp_path / "workspace" / "shared_assets" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "a.mp4").write_bytes(b"a")

    captured_videos: list[str] = []

    def _fake_ingest_one(self, video_path, output_base, log_callback=None):
        captured_videos.append(video_path.name)
        return []

    monkeypatch.setattr(
        "packages.pipeline_services.asset_library.indexer.AssetIndexer._ingest_one_video",
        _fake_ingest_one,
    )

    resp = client.post(
        "/api/assets/index",
        params={"async_mode": False},
        json={"source_paths": []},
    )

    assert resp.status_code == 200
    assert captured_videos == []


def test_index_source_paths_async_respected(tmp_path: Path) -> None:
    """异步模式的 source_paths 也只索引指定文件。"""
    client = _client(tmp_path)
    source_dir = tmp_path / "workspace" / "shared_assets" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "a.mp4").write_bytes(b"a")
    (source_dir / "b.mp4").write_bytes(b"b")
    (source_dir / "c.mp4").write_bytes(b"c")

    resp = client.post(
        "/api/assets/index",
        params={"async_mode": True},
        json={"source_paths": ["a.mp4", "c.mp4"]},
    )

    assert resp.status_code == 200
    data = resp.json()
    # total_videos 应只反映 source_paths 中的 2 个而非全部 3 个
    assert data["total_videos"] == 2, (
        f"期望 total_videos=2 (source_paths 限定的文件数)，实际: {data['total_videos']}"
    )
