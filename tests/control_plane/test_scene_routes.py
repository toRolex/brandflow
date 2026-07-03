"""Tests for scene segment management API routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _make_client(tmp_path: Path, scene_folders: list[dict] | None = None):
    """Create a test client with optional scene config."""
    if scene_folders is not None:
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "app_config.json"
        config_path.write_bytes(
            json.dumps(
                {
                    "scene": {
                        "folders": scene_folders,
                        "transition_duration_ms": 500,
                    }
                },
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")
        )
    return TestClient(create_app(root_dir=tmp_path))


# ── POST /api/scene/upload ──────────────────────────────────────────


def test_upload_valid_file(tmp_path: Path) -> None:
    """Upload a valid mp4 file to an existing scene folder."""
    folders = [
        {"name": "品牌开场", "path": "brand-intro"},
    ]
    client = _make_client(tmp_path, folders)

    content = b"fake video content"
    resp = client.post(
        "/api/scene/upload?folder=brand-intro",
        files={"file": ("intro.mp4", content, "video/mp4")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["folder"] == "brand-intro"
    assert data["size_bytes"] == len(content)
    assert data["name"].endswith("intro.mp4")
    # File should exist on disk
    saved_path = tmp_path / "workspace" / "scene" / "brand-intro" / data["name"]
    assert saved_path.exists()
    assert saved_path.read_bytes() == content


def test_upload_invalid_folder(tmp_path: Path) -> None:
    """Upload to a non-existent folder returns 400."""
    client = _make_client(tmp_path, [])
    content = b"fake video"
    resp = client.post(
        "/api/scene/upload?folder=nonexistent",
        files={"file": ("test.mp4", content, "video/mp4")},
    )
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"]


def test_upload_invalid_file_type(tmp_path: Path) -> None:
    """Upload a non-video file type returns 400."""
    folders = [{"name": "产品展示", "path": "product-showcase"}]
    client = _make_client(tmp_path, folders)
    resp = client.post(
        "/api/scene/upload?folder=product-showcase",
        files={"file": ("doc.pdf", b"pdf content", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "Invalid file type" in resp.json()["detail"]


def test_upload_no_filename(tmp_path: Path) -> None:
    """Upload without filename returns 422 (FastAPI validation)."""
    folders = [{"name": "产品展示", "path": "product-showcase"}]
    client = _make_client(tmp_path, folders)
    resp = client.post(
        "/api/scene/upload?folder=product-showcase",
        files={"file": ("", b"content", "video/mp4")},
    )
    assert resp.status_code == 422


def test_upload_multiple_formats(tmp_path: Path) -> None:
    """All allowed video formats are accepted."""
    folders = [{"name": "品牌开场", "path": "brand-intro"}]
    client = _make_client(tmp_path, folders)
    for ext in [".mp4", ".mov", ".avi", ".webm"]:
        content = f"fake {ext} content".encode()
        resp = client.post(
            "/api/scene/upload?folder=brand-intro",
            files={"file": (f"video{ext}", content, f"video/{ext[1:]}")},
        )
        assert resp.status_code == 200, f"Failed for extension {ext}"
        data = resp.json()
        assert data["size_bytes"] == len(content)
        assert data["name"].endswith(f"video{ext}")


# ── GET /api/scene/folders ──────────────────────────────────────────


def test_list_folders_empty(tmp_path: Path) -> None:
    """Empty scene config returns empty folders list."""
    client = _make_client(tmp_path, [])
    resp = client.get("/api/scene/folders")
    assert resp.status_code == 200
    data = resp.json()
    assert data["folders"] == []
    assert data["transition_duration_ms"] == 500


def test_list_folders_with_counts(tmp_path: Path) -> None:
    """Folders list includes file counts from disk."""
    folders = [
        {"name": "品牌开场", "path": "brand-intro"},
        {"name": "产品展示", "path": "product-showcase"},
    ]
    client = _make_client(tmp_path, folders)

    # Add files to brand-intro
    scene_dir = tmp_path / "workspace" / "scene" / "brand-intro"
    scene_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (scene_dir / f"clip_{i}.mp4").write_bytes(b"content")

    # Add files to product-showcase
    scene_dir2 = tmp_path / "workspace" / "scene" / "product-showcase"
    scene_dir2.mkdir(parents=True, exist_ok=True)
    (scene_dir2 / "demo.mp4").write_bytes(b"content")
    # Non-video file should not count
    (scene_dir2 / "note.txt").write_bytes(b"not a video")

    resp = client.get("/api/scene/folders")
    assert resp.status_code == 200
    data = resp.json()
    assert data["transition_duration_ms"] == 500
    folder_map = {f["path"]: f for f in data["folders"]}
    assert folder_map["brand-intro"]["file_count"] == 3
    assert folder_map["product-showcase"]["file_count"] == 1


# ── GET /api/scene/folders/{folder_name}/files ──────────────────────


def test_list_files_in_folder(tmp_path: Path) -> None:
    """List files returns metadata for all video files in the folder."""
    folders = [{"name": "品牌开场", "path": "brand-intro"}]
    client = _make_client(tmp_path, folders)

    scene_dir = tmp_path / "workspace" / "scene" / "brand-intro"
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "clip_001.mp4").write_bytes(b"content1")
    (scene_dir / "clip_002.mp4").write_bytes(b"content2" * 1000)

    resp = client.get("/api/scene/folders/brand-intro/files")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["files"]) == 2
    names = {f["name"] for f in data["files"]}
    assert names == {"clip_001.mp4", "clip_002.mp4"}
    for f in data["files"]:
        assert "size_bytes" in f
        assert "uploaded_at" in f


def test_list_files_nonexistent_folder(tmp_path: Path) -> None:
    """Listing files for a non-configured folder returns 404."""
    client = _make_client(tmp_path, [])
    resp = client.get("/api/scene/folders/nonexistent/files")
    assert resp.status_code == 404


def test_list_files_empty_folder(tmp_path: Path) -> None:
    """Empty scene folder returns empty files list."""
    folders = [{"name": "品牌开场", "path": "brand-intro"}]
    client = _make_client(tmp_path, folders)
    resp = client.get("/api/scene/folders/brand-intro/files")
    assert resp.status_code == 200
    assert resp.json()["files"] == []


# ── DELETE /api/scene/folders/{folder_name}/files/{file_name} ───────


def test_delete_file_success(tmp_path: Path) -> None:
    """Delete a file returns 204 and removes it from disk."""
    folders = [{"name": "品牌开场", "path": "brand-intro"}]
    client = _make_client(tmp_path, folders)

    scene_dir = tmp_path / "workspace" / "scene" / "brand-intro"
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "clip_001.mp4").write_bytes(b"content")

    resp = client.delete("/api/scene/folders/brand-intro/files/clip_001.mp4")
    assert resp.status_code == 204
    assert not (scene_dir / "clip_001.mp4").exists()


def test_delete_file_not_found(tmp_path: Path) -> None:
    """Delete a non-existent file returns 404."""
    folders = [{"name": "品牌开场", "path": "brand-intro"}]
    client = _make_client(tmp_path, folders)

    resp = client.delete("/api/scene/folders/brand-intro/files/nonexistent.mp4")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_delete_file_nonexistent_folder(tmp_path: Path) -> None:
    """Delete from a non-configured folder returns 404."""
    client = _make_client(tmp_path, [])
    resp = client.delete("/api/scene/folders/nonexistent/files/some.mp4")
    assert resp.status_code == 404
