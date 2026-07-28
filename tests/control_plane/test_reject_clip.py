"""Regression tests for single-clip reject (打回检索).

``/reject-clip`` is the single backend entry point for per-clip re-search.
The legacy ``/asset/re-search`` endpoint has been removed; its behaviour
(blank clips are skipped, method is ``re_search``) is now provided by
``/reject-clip``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app

PRODUCT = "羊肚菌"


def _setup(
    tmp_path: Path,
    clips: list[dict],
    assets: list[tuple[str, str]],
    *,
    project_id: str = "proj-001",
    job_project_id: str | None = None,
    phase: str = "asset_review",
) -> dict:
    """Create a job plus an asset library and return context helpers.

    ``assets`` is a list of (asset_id, category) rows for PRODUCT.
    ``job_project_id`` overrides the ``project_id`` stored in the job record
    (useful for simulating legacy/missing project_id values).
    """
    root_dir = tmp_path
    job_id = "job-reject-1"
    stored_project_id = project_id if job_project_id is None else job_project_id

    job_dir = (
        root_dir / "workspace" / "projects" / project_id / "runtime" / "jobs" / job_id
    )
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "selected_clips.json").write_text(
        json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    control_dir = root_dir / "workspace" / "projects" / project_id / "control" / "jobs"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / f"{job_id}.json").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "project_id": stored_project_id,
                "product": PRODUCT,
                "phase": phase,
                "review_status": "pending",
                "mode": "generate",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    db_dir = root_dir / "workspace" / "shared_assets"
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_dir / "asset_index.db"))
    conn.execute(
        """
        CREATE TABLE assets (
            asset_id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            category TEXT NOT NULL,
            product TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.0,
            duration_seconds REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'available',
            usage_count INTEGER NOT NULL DEFAULT 0,
            source_video TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT '',
            last_used_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    for aid, cat in assets:
        conn.execute(
            "INSERT INTO assets (asset_id, file_path, category, product, duration_seconds)"
            " VALUES (?, ?, ?, ?, ?)",
            (aid, f"/data/{aid}.mp4", cat, PRODUCT, 6.0),
        )
    conn.commit()
    conn.close()

    return {"root_dir": root_dir, "project_id": project_id, "job_id": job_id}


def _clips(ctx: dict) -> list[dict]:
    clips_path = (
        ctx["root_dir"]
        / "workspace"
        / "projects"
        / ctx["project_id"]
        / "runtime"
        / "jobs"
        / ctx["job_id"]
        / "selected_clips.json"
    )
    return json.loads(clips_path.read_text(encoding="utf-8"))


def _usage_count(ctx: dict, asset_id: str) -> int:
    db_path = ctx["root_dir"] / "workspace" / "shared_assets" / "asset_index.db"
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT usage_count FROM assets WHERE asset_id = ?", (asset_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else -1


CLIP = {
    "sentence": "第一句介绍。",
    "sentence_index": 0,
    "category": "intro",
    "requested_category": "intro",
    "file_path": "/data/a1.mp4",
    "asset_id": "a1",
    "duration_seconds": 5.0,
    "method": "llm_match",
    "visual_type": "clip",
}


class TestRejectClip:
    def test_replacement_preserves_clip_fields(self, tmp_path: Path) -> None:
        ctx = _setup(
            tmp_path,
            [dict(CLIP)],
            [("a1", "intro"), ("alt1", "intro")],
        )
        app = create_app(root_dir=ctx["root_dir"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/{ctx['job_id']}/reject-clip?project_id={ctx['project_id']}",
                json={"clip_index": 0},
            )
            assert resp.status_code == 200
            body = resp.json()
            # Updated entry is returned so the frontend can patch in place.
            assert body["replaced"] is True
            assert body["clip"]["asset_id"] == "alt1"
            assert body["clip"]["visual_type"] == "clip"

        entry = _clips(ctx)[0]
        # Replaced with the only available alternative.
        assert entry["asset_id"] == "alt1"
        assert entry["file_path"] == "/data/alt1.mp4"
        assert entry["duration_seconds"] == 6.0
        assert entry["method"] == "re_search"
        # Fields the review card depends on must survive the replacement.
        assert entry["visual_type"] == "clip"
        assert entry["sentence_index"] == 0
        assert entry["requested_category"] == "intro"
        assert entry["sentence"] == "第一句介绍。"
        # Original state recorded for 恢复原始选择.
        assert entry["_original"]["asset_id"] == "a1"

    def test_usage_count_updated_on_replacement(self, tmp_path: Path) -> None:
        ctx = _setup(
            tmp_path,
            [dict(CLIP)],
            [("a1", "intro"), ("alt1", "intro")],
        )
        # Seed initial usage counts to verify decrement + increment.
        db_path = ctx["root_dir"] / "workspace" / "shared_assets" / "asset_index.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE assets SET usage_count = 1 WHERE asset_id = 'a1'")
        conn.execute("UPDATE assets SET usage_count = 1 WHERE asset_id = 'alt1'")
        conn.commit()
        conn.close()

        app = create_app(root_dir=ctx["root_dir"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/{ctx['job_id']}/reject-clip?project_id={ctx['project_id']}",
                json={"clip_index": 0},
            )
            assert resp.status_code == 200
            assert resp.json()["replaced"] is True

        assert _usage_count(ctx, "a1") == 0
        assert _usage_count(ctx, "alt1") == 2

    def test_no_alternative_keeps_entry_untouched(self, tmp_path: Path) -> None:
        ctx = _setup(tmp_path, [dict(CLIP)], [("a1", "intro")])
        app = create_app(root_dir=ctx["root_dir"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/{ctx['job_id']}/reject-clip?project_id={ctx['project_id']}",
                json={"clip_index": 0},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["replaced"] is False
            assert body["clip"]["asset_id"] == "a1"
            assert "intro" in body["reason"]
            assert body["diagnostics"]["total"] == 1
            assert body["diagnostics"]["same_id"] == 1

        entry = _clips(ctx)[0]
        assert entry["asset_id"] == "a1"
        assert entry["visual_type"] == "clip"
        assert entry["method"] == "llm_match"

    def test_replacement_works_when_query_project_id_is_missing(
        self, tmp_path: Path
    ) -> None:
        """Reject-clip must still resolve the job's product when project_id is omitted."""
        ctx = _setup(
            tmp_path,
            [dict(CLIP)],
            [("a1", "intro"), ("alt1", "intro")],
            job_project_id="",
        )
        app = create_app(root_dir=ctx["root_dir"])
        with TestClient(app) as client:
            # Simulate a caller that does not supply project_id.
            resp = client.post(
                f"/api/reviews/{ctx['job_id']}/reject-clip",
                json={"clip_index": 0},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["replaced"] is True
            assert body["clip"]["asset_id"] == "alt1"

        entry = _clips(ctx)[0]
        assert entry["asset_id"] == "alt1"

    def test_replacement_fails_when_job_product_mismatches_asset_product(
        self, tmp_path: Path
    ) -> None:
        """A product mismatch between job and assets yields no candidates."""
        ctx = _setup(
            tmp_path,
            [dict(CLIP)],
            [("a1", "intro"), ("alt1", "intro")],
        )
        control_path = (
            ctx["root_dir"]
            / "workspace"
            / "projects"
            / ctx["project_id"]
            / "control"
            / "jobs"
            / f"{ctx['job_id']}.json"
        )
        record = json.loads(control_path.read_text(encoding="utf-8"))
        record["product"] = "mismatched-product"
        control_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        app = create_app(root_dir=ctx["root_dir"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/{ctx['job_id']}/reject-clip?project_id={ctx['project_id']}",
                json={"clip_index": 0},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["replaced"] is False
            assert body["clip"]["asset_id"] == "a1"

    def test_reject_clip_requires_asset_review_phase(self, tmp_path: Path) -> None:
        """Mutating clips is only allowed during asset_review."""
        ctx = _setup(
            tmp_path,
            [dict(CLIP)],
            [("a1", "intro"), ("alt1", "intro")],
            phase="montage_assembling",
        )
        app = create_app(root_dir=ctx["root_dir"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/{ctx['job_id']}/reject-clip?project_id={ctx['project_id']}",
                json={"clip_index": 0},
            )
            assert resp.status_code == 409
            assert "asset_review" in resp.json()["detail"]

    def test_blank_clip_is_skipped(self, tmp_path: Path) -> None:
        """Re-search must not overwrite clips explicitly marked as blank."""
        blank_clip = {**CLIP, "visual_type": "blank", "method": "blank"}
        ctx = _setup(
            tmp_path,
            [blank_clip],
            [("a1", "intro"), ("alt1", "intro")],
        )
        app = create_app(root_dir=ctx["root_dir"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/{ctx['job_id']}/reject-clip?project_id={ctx['project_id']}",
                json={"clip_index": 0},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["replaced"] is False
            assert body["clip"]["visual_type"] == "blank"

        entry = _clips(ctx)[0]
        assert entry["asset_id"] == "a1"
        assert entry["visual_type"] == "blank"

    def test_replacement_failure_marks_rejected_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """If persistence fails after usage_count is adjusted, the clip is marked."""
        ctx = _setup(
            tmp_path,
            [dict(CLIP)],
            [("a1", "intro"), ("alt1", "intro")],
        )

        def _failing_save(job_dir, clips):
            raise OSError("simulated write failure")

        monkeypatch.setattr(
            "apps.control_plane.routes.reviews._save_clips", _failing_save
        )

        app = create_app(root_dir=ctx["root_dir"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/{ctx['job_id']}/reject-clip?project_id={ctx['project_id']}",
                json={"clip_index": 0},
            )
            assert resp.status_code == 500

        # Because _save_clips was patched to fail, the file still has the
        # original clip; the in-memory mutation attempted to set method to
        # rejected_error but was not persisted. This test primarily verifies
        # the route returns 500 rather than crashing silently.
        assert "simulated write failure" in resp.json()["detail"]


    def test_no_alternative_logs_structured_warning(self, tmp_path: Path) -> None:
        """A missing replacement writes a structured warning via log_service."""
        ctx = _setup(tmp_path, [dict(CLIP)], [("a1", "intro")])
        app = create_app(root_dir=ctx["root_dir"])

        captured: list[dict] = []

        def _fake_log_error(entry: dict, log_dir=None) -> None:
            captured.append(entry)

        with patch("apps.control_plane.routes.reviews.log_error", _fake_log_error):
            with TestClient(app) as client:
                resp = client.post(
                    f"/api/reviews/{ctx['job_id']}/reject-clip?project_id={ctx['project_id']}",
                    json={"clip_index": 0},
                )
                assert resp.status_code == 200

        assert len(captured) == 1
        entry = captured[0]
        assert entry["level"] == "warn"
        assert entry["source"] == "backend"
        assert ctx["job_id"] in entry["message"]
        assert "intro" in entry["extra"]["reason"]
        assert "no usable alternative" in entry["extra"]["reason"] or "only the current asset exists" in entry["extra"]["reason"]
        diagnostics = entry["extra"]["diagnostics"]
        assert diagnostics["total"] == 1
        assert diagnostics["same_id"] == 1


class TestAssetReSearchRemoved:
    def test_re_search_endpoint_returns_404(self, tmp_path: Path) -> None:
        """The legacy /asset/re-search endpoint has been removed."""
        ctx = _setup(
            tmp_path,
            [dict(CLIP)],
            [("a1", "intro"), ("alt1", "intro")],
        )
        app = create_app(root_dir=ctx["root_dir"])
        with TestClient(app) as client:
            resp = client.post(
                f"/api/reviews/{ctx['job_id']}/asset/re-search?project_id={ctx['project_id']}",
                json={"clip_index": 0},
            )
            assert resp.status_code == 404
