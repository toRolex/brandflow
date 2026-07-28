"""Regression tests for single-clip reject (打回检索) and asset re-search.

The legacy ``/reject-clip`` endpoint used to *replace* the whole clip entry,
dropping ``visual_type`` / ``sentence_index`` / ``requested_category`` /
``duration_seconds`` — the review card then rendered the clip as
"待处理/未匹配到素材" and the single-clip re-search looked broken.

The ``/asset/re-search`` endpoint queried candidates with
``entry.get("product", "")``, but selected_clips entries never carry a
``product`` field, so it could never find a replacement.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

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
) -> dict:
    """Create a job in asset_review plus an asset library.

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
                "phase": "asset_review",
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
        assert entry["method"] == "rejected_replaced"
        # Fields the review card depends on must survive the replacement.
        assert entry["visual_type"] == "clip"
        assert entry["sentence_index"] == 0
        assert entry["requested_category"] == "intro"
        assert entry["sentence"] == "第一句介绍。"
        # Original state recorded for 恢复原始选择.
        assert entry["_original"]["asset_id"] == "a1"

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

        entry = _clips(ctx)[0]
        assert entry["asset_id"] == "a1"
        assert entry["visual_type"] == "clip"
        assert entry["method"] == "llm_match"

    def test_replacement_works_when_query_project_id_is_missing(self, tmp_path: Path) -> None:
        """Reject-clip must still resolve the job's product when project_id is omitted.

        The endpoint's internal job-dir resolution can fall back to scanning all
        projects, but the product lookup must use the canonical job record rather
        than an empty/missing query-project_id path.
        """
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
        """A product mismatch between job and assets yields no candidates.

        This captures the real-world failure mode where the asset library was
        indexed under a different product name than the current job uses, so
        reject-clip cannot find any alternative and misleadingly reports
        "该分类下没有可替代的素材".
        """
        # Override the job record to use a different product than the assets.
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


class TestAssetReSearch:
    def test_re_search_uses_job_product_and_excludes_current(
        self, tmp_path: Path
    ) -> None:
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
            assert resp.status_code == 200
            assert resp.json()["visual_type"] == "clip"

        entry = _clips(ctx)[0]
        # Must not silently keep/re-pick the rejected asset.
        assert entry["asset_id"] == "alt1"
        assert entry["visual_type"] == "clip"
        assert entry["method"] == "re_search"
