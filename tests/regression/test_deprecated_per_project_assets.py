"""Regression tests for DEPRECATED per-project asset endpoints.

These endpoints are deprecated in favor of global /api/assets endpoints.
These tests verify they remain functional until removal.

See: apps/control_plane/routes/api_projects.py
"""

import sqlite3
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from apps.control_plane.app import create_app
from packages.file_store.repository import FileStoreRepository


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_app_with_project(root_dir: Path, project_id: str = "test-prj"):
    """Create app + project, return (app, project_id)."""
    app = create_app(root_dir=root_dir)
    repo = FileStoreRepository(root_dir)
    repo.create_project(project_id)
    return app, project_id


def _create_asset_db(project_dir: Path, assets: list[dict]) -> Path:
    """Create a per-project asset_index.db with the given assets."""
    db_path = project_dir / "asset_index.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            file_path TEXT,
            category TEXT,
            product TEXT,
            confidence REAL,
            duration_seconds REAL,
            status TEXT,
            usage_count INTEGER,
            source_video TEXT,
            tags TEXT,
            created_at TEXT,
            last_used_at TEXT
        )"""
    )
    for a in assets:
        conn.execute(
            """INSERT OR REPLACE INTO assets
               (asset_id, file_path, category, product, confidence, duration_seconds,
                status, usage_count, source_video, tags, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                a["asset_id"],
                a.get("file_path", f"/tmp/{a['asset_id']}.mp4"),
                a.get("category", ""),
                a.get("product", ""),
                a.get("confidence", 0.9),
                a.get("duration_seconds", 5.0),
                a.get("status", "available"),
                a.get("usage_count", 0),
                a.get("source_video", ""),
                a.get("tags", "[]"),
                a.get("created_at", "2025-01-01T00:00:00"),
                a.get("last_used_at", "2025-01-01T00:00:00"),
            ),
        )
    conn.commit()
    conn.close()
    return db_path


# ======================================================================
# POST /api/projects/{project_id}/upload
# ======================================================================


class TestUploadAsset:
    """DEPRECATED per-project upload endpoint."""

    def test_upload_asset(self):
        """Upload a file to project source_assets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            resp = client.post(
                f"/api/projects/{pid}/upload",
                files={"file": ("test.mp4", b"fake video content")},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "test.mp4"
            assert data["size_bytes"] == 18
            assert data["in_use"] is False

    def test_upload_asset_empty_filename_returns_400(self):
        """Upload with empty filename returns 400."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            # Starlette normalizes empty filename to 422 before reaching handler
            resp = client.post(
                f"/api/projects/{pid}/upload",
                files={"file": ("", b"content")},
            )
            assert resp.status_code == 422

    def test_upload_asset_creates_project_implicitly(self):
        """Upload with new project_id creates the project automatically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app = create_app(root_dir=root)
            client = TestClient(app)

            # Upload to a project that doesn't exist yet
            resp = client.post(
                "/api/projects/new-prj/upload",
                files={"file": ("clip.mp4", b"data")},
            )
            assert resp.status_code == 200

            # Verify project was created
            repo = FileStoreRepository(root)
            assets = repo.list_assets("new-prj")
            assert len(assets) == 1
            assert assets[0]["name"] == "clip.mp4"


# ======================================================================
# GET /api/projects/{project_id}/assets
# ======================================================================


class TestListAssets:
    """DEPRECATED per-project list endpoint."""

    def test_list_assets_empty(self):
        """Project with no source assets returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            resp = client.get(f"/api/projects/{pid}/assets")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_list_assets_with_files(self):
        """List returns uploaded files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            # Upload a file
            client.post(
                f"/api/projects/{pid}/upload",
                files={"file": ("a.mp4", b"aaa")},
            )

            resp = client.get(f"/api/projects/{pid}/assets")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["name"] == "a.mp4"
            assert data[0]["in_use"] is False

    def test_list_assets_multiple_files(self):
        """List returns multiple files sorted by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            client.post(
                f"/api/projects/{pid}/upload",
                files={"file": ("b.mp4", b"bbb")},
            )
            client.post(
                f"/api/projects/{pid}/upload",
                files={"file": ("a.mp4", b"aaa")},
            )

            resp = client.get(f"/api/projects/{pid}/assets")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            assert data[0]["name"] == "a.mp4"
            assert data[1]["name"] == "b.mp4"

    def test_list_assets_nonexistent_project(self):
        """Nonexistent project returns empty list (not 404)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app = create_app(root_dir=root)
            client = TestClient(app)

            resp = client.get("/api/projects/no-such-prj/assets")
            assert resp.status_code == 200
            assert resp.json() == []


# ======================================================================
# GET /api/projects/{project_id}/assets/indexed
# ======================================================================


class TestGetIndexedAssets:
    """DEPRECATED per-project indexed-assets endpoint."""

    def test_indexed_assets_nonexistent_project_returns_404(self):
        """Project not found returns 404."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app = create_app(root_dir=root)
            client = TestClient(app)

            resp = client.get("/api/projects/ghost/assets/indexed")
            assert resp.status_code == 404

    def test_indexed_assets_no_db_returns_empty(self):
        """Project without asset_index.db returns empty stats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            resp = client.get(f"/api/projects/{pid}/assets/indexed")
            assert resp.status_code == 200
            data = resp.json()
            assert data["assets"] == []
            assert data["stats"]["total_clips"] == 0

    def test_indexed_assets_returns_all(self):
        """Project with populated DB returns all assets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            project_dir = root / "workspace" / "projects" / pid
            _create_asset_db(
                project_dir,
                [
                    {
                        "asset_id": "a1",
                        "file_path": "/tmp/a1.mp4",
                        "category": "冲泡",
                        "product": "龙井茶",
                    },
                    {
                        "asset_id": "a2",
                        "file_path": "/tmp/a2.mp4",
                        "category": "产地",
                        "product": "龙井茶",
                    },
                ],
            )

            resp = client.get(f"/api/projects/{pid}/assets/indexed")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["assets"]) == 2
            assert data["stats"]["total_clips"] == 2

    def test_indexed_assets_filters_by_product(self):
        """Product filter returns only matching assets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            project_dir = root / "workspace" / "projects" / pid
            _create_asset_db(
                project_dir,
                [
                    {
                        "asset_id": "a1",
                        "file_path": "/tmp/a1.mp4",
                        "product": "龙井茶",
                        "category": "冲泡",
                    },
                    {
                        "asset_id": "a2",
                        "file_path": "/tmp/a2.mp4",
                        "product": "龙井茶",
                        "category": "产地",
                    },
                    {
                        "asset_id": "a3",
                        "file_path": "/tmp/a3.mp4",
                        "product": "普洱茶",
                        "category": "冲泡",
                    },
                ],
            )

            resp = client.get(
                f"/api/projects/{pid}/assets/indexed",
                params={"product": "龙井茶"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["assets"]) == 2
            assert {a["asset_id"] for a in data["assets"]} == {"a1", "a2"}

    def test_indexed_assets_combined_filters(self):
        """Product + category filters combine with AND."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            project_dir = root / "workspace" / "projects" / pid
            _create_asset_db(
                project_dir,
                [
                    {
                        "asset_id": "a1",
                        "file_path": "/tmp/a1.mp4",
                        "product": "龙井茶",
                        "category": "冲泡",
                    },
                    {
                        "asset_id": "a2",
                        "file_path": "/tmp/a2.mp4",
                        "product": "龙井茶",
                        "category": "产地",
                    },
                    {
                        "asset_id": "a3",
                        "file_path": "/tmp/a3.mp4",
                        "product": "普洱茶",
                        "category": "冲泡",
                    },
                ],
            )

            resp = client.get(
                f"/api/projects/{pid}/assets/indexed",
                params={"product": "龙井茶", "category": "冲泡"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["assets"]) == 1
            assert data["assets"][0]["asset_id"] == "a1"

    def test_indexed_assets_search_by_q(self):
        """Text search filter (q) matches file_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            project_dir = root / "workspace" / "projects" / pid
            _create_asset_db(
                project_dir,
                [
                    {"asset_id": "a1", "file_path": "/tmp/hero.mp4"},
                    {"asset_id": "a2", "file_path": "/tmp/background.mp4"},
                ],
            )

            resp = client.get(
                f"/api/projects/{pid}/assets/indexed",
                params={"q": "hero"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["assets"]) == 1
            assert data["assets"][0]["asset_id"] == "a1"


# ======================================================================
# POST /api/projects/{project_id}/assets/index
# ======================================================================


class TestIndexAssets:
    """DEPRECATED per-project index endpoint."""

    def test_index_assets_nonexistent_project_returns_404(self):
        """Index on nonexistent project returns 404."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app = create_app(root_dir=root)
            client = TestClient(app)

            resp = client.post("/api/projects/ghost/assets/index")
            assert resp.status_code == 404

    def test_index_assets_empty_returns_zero(self):
        """Index with no source videos returns 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            resp = client.post(f"/api/projects/{pid}/assets/index")
            assert resp.status_code == 200
            data = resp.json()
            assert data["indexed"] == 0
            assert data["skipped"] == 0
            assert data["total_clips"] == 0


# ======================================================================
# PATCH /api/projects/{project_id}/assets/{asset_id}
# ======================================================================


class TestPatchAssetStatus:
    """DEPRECATED per-project asset status update (single & batch)."""

    def test_patch_single_asset_status(self):
        """Update a single asset's status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            project_dir = root / "workspace" / "projects" / pid
            _create_asset_db(
                project_dir,
                [
                    {
                        "asset_id": "a1",
                        "file_path": "/tmp/a1.mp4",
                        "status": "available",
                    },
                ],
            )

            resp = client.patch(
                f"/api/projects/{pid}/assets/a1",
                json={"status": "disabled"},
            )
            assert resp.status_code == 200
            assert resp.json()["updated"] == 1

            # Verify DB
            conn = sqlite3.connect(str(project_dir / "asset_index.db"))
            updated = conn.execute(
                "SELECT status FROM assets WHERE asset_id = ?", ("a1",)
            ).fetchone()[0]
            conn.close()
            assert updated == "disabled"

    def test_patch_batch_asset_status(self):
        """Batch-update multiple assets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            project_dir = root / "workspace" / "projects" / pid
            _create_asset_db(
                project_dir,
                [
                    {
                        "asset_id": "a1",
                        "file_path": "/tmp/a1.mp4",
                        "status": "available",
                    },
                    {
                        "asset_id": "a2",
                        "file_path": "/tmp/a2.mp4",
                        "status": "available",
                    },
                    {
                        "asset_id": "a3",
                        "file_path": "/tmp/a3.mp4",
                        "status": "available",
                    },
                ],
            )

            resp = client.patch(
                f"/api/projects/{pid}/assets/batch",
                json={"status": "disabled", "asset_ids": ["a1", "a3"]},
            )
            assert resp.status_code == 200
            assert resp.json()["updated"] == 2

            conn = sqlite3.connect(str(project_dir / "asset_index.db"))
            rows = conn.execute(
                "SELECT asset_id, status FROM assets ORDER BY asset_id"
            ).fetchall()
            conn.close()
            statuses = dict(rows)
            assert statuses["a1"] == "disabled"
            assert statuses["a2"] == "available"
            assert statuses["a3"] == "disabled"

    def test_patch_invalid_status_returns_400(self):
        """Invalid status value returns 400."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            resp = client.patch(
                f"/api/projects/{pid}/assets/a1",
                json={"status": "invalid_status"},
            )
            assert resp.status_code == 400

    def test_patch_nonexistent_project_returns_404(self):
        """Project not found returns 404."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app = create_app(root_dir=root)
            client = TestClient(app)

            resp = client.patch(
                "/api/projects/ghost/assets/a1",
                json={"status": "disabled"},
            )
            assert resp.status_code == 404

    def test_patch_no_db_returns_updated_zero(self):
        """Project without asset_index.db returns updated=0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            resp = client.patch(
                f"/api/projects/{pid}/assets/a1",
                json={"status": "disabled"},
            )
            assert resp.status_code == 200
            assert resp.json()["updated"] == 0

    def test_patch_pending_review_status(self):
        """pending_review is a valid status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            project_dir = root / "workspace" / "projects" / pid
            _create_asset_db(
                project_dir,
                [
                    {
                        "asset_id": "a1",
                        "file_path": "/tmp/a1.mp4",
                        "status": "available",
                    },
                ],
            )

            resp = client.patch(
                f"/api/projects/{pid}/assets/a1",
                json={"status": "pending_review"},
            )
            assert resp.status_code == 200
            assert resp.json()["updated"] == 1

    def test_patch_batch_empty_asset_ids_returns_400(self):
        """Batch mode with empty asset_ids returns 400."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            resp = client.patch(
                f"/api/projects/{pid}/assets/batch",
                json={"status": "disabled", "asset_ids": []},
            )
            assert resp.status_code == 400

    def test_patch_batch_without_asset_ids_returns_400(self):
        """Batch mode without asset_ids returns 400."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            resp = client.patch(
                f"/api/projects/{pid}/assets/batch",
                json={"status": "disabled"},
            )
            assert resp.status_code == 400


# ======================================================================
# DELETE /api/projects/{project_id}/assets/{asset_name}
# ======================================================================


class TestDeleteAsset:
    """DEPRECATED per-project asset delete endpoint.

    Note: the route's ``_sanitize_filename`` guard (rejects names containing ``/``)
    is not exercisable via TestClient because Starlette normalizes path segments
    before routing. It is validated by code inspection only.
    """

    def test_delete_asset(self):
        """Delete an existing source asset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            source_dir = (
                root / "workspace" / "projects" / pid / "runtime" / "source_assets"
            )
            source_dir.mkdir(parents=True, exist_ok=True)
            (source_dir / "test.mp4").write_bytes(b"content")

            resp = client.delete(f"/api/projects/{pid}/assets/test.mp4")
            assert resp.status_code == 200
            assert resp.json()["status"] == "deleted"
            assert not (source_dir / "test.mp4").exists()

    def test_delete_asset_nonexistent_returns_404(self):
        """Delete nonexistent asset returns 404."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            resp = client.delete(f"/api/projects/{pid}/assets/no-such-file.mp4")
            assert resp.status_code == 404

    def test_delete_asset_invalid_name_returns_404(self):
        """Asset name with raw path separator is normalized by Starlette to a
        different route, resulting in 404."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app, pid = _build_app_with_project(root)
            client = TestClient(app)

            # The raw ``/`` in ``subdir/file.mp4`` is treated as a path segment
            # by Starlette, so this never reaches the DELETE handler.
            resp = client.delete(f"/api/projects/{pid}/assets/subdir/file.mp4")
            assert resp.status_code == 404
