"""Tests: Scene Asset Snapshot per-entry invalidation (issue #174 AC-6).

Verifies that when source files change, only the invalidated manifest entries
are re-randomized while valid entries reuse the snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
    PhaseOrchestrator,
)


class FakeVideoService:
    def build_base_video(self, *args, **kwargs):
        return []


class FakeSubtitleService:
    def build_srt(self, *args, **kwargs):
        pass


class TestSceneSnapshotPartialInvalidation:
    """Manifest entries are invalidated per-entry (not all-or-nothing)."""

    def _make_orchestrator(self) -> PhaseOrchestrator:
        return PhaseOrchestrator(
            subtitle_svc=FakeSubtitleService(),
            video_svc=FakeVideoService(),
        )

    def _setup_workspace(
        self, tmp_path: Path, n_folders: int = 3, files_per_folder: int = 2
    ) -> tuple[PhaseOrchestrator, PhaseContext, Path]:
        """Create a workspace with scene folders each containing video files."""
        orch = self._make_orchestrator()

        folders: list[Path] = []
        for i in range(n_folders):
            folder = tmp_path / f"scene_folder_{i}"
            folder.mkdir(parents=True)
            for j in range(files_per_folder):
                video = folder / f"clip_{j}.mp4"
                video.write_bytes(f"fake_video_{i}_{j}".encode())
            folders.append(folder)

        ctx = PhaseContext(
            job_id="test-snapshot",
            project_dir=tmp_path / "project",
            root_dir=tmp_path,
            product="test",
            scene_folder_paths=[str(f) for f in folders],
        )
        ctx.project_dir.mkdir(parents=True, exist_ok=True)

        # Also patch orch to not use real ffmpeg
        orch._get_ffmpeg_path = lambda: "ffmpeg"
        orch._get_media_duration = lambda p: 5.0

        return orch, ctx, tmp_path

    def test_full_snapshot_reuse(self, tmp_path: Path):
        """All entries match → all reuse snapshot, no re-randomize."""
        orch, ctx, root = self._setup_workspace(tmp_path)
        job_dir = orch._job_dir(ctx)

        # First run: create snapshot
        patches = [
            patch(
                "packages.pipeline_services.phase_orchestrator.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ),
        ]
        with patches[0]:
            orch._run_scene_assembly(ctx)

        manifest_path = job_dir / ".scene_snapshot" / "manifest.json"
        assert manifest_path.exists(), "Snapshot should exist after first run"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert len(manifest) == 3, f"Expected 3 entries, got {len(manifest)}"

        # Second run: all fingerprints should still match
        with patches[0]:
            orch._run_scene_assembly(ctx)

        # Manifest should not have changed
        manifest2 = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest2 == manifest, "Manifest should be identical on valid reuse"

    def test_partial_invalidation(self, tmp_path: Path):
        """One entry's source changes → only that entry is re-randomized."""
        orch, ctx, root = self._setup_workspace(tmp_path, files_per_folder=5)
        job_dir = orch._job_dir(ctx)

        patches = [
            patch(
                "packages.pipeline_services.phase_orchestrator.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ),
        ]
        with patches[0]:
            orch._run_scene_assembly(ctx)

        manifest_path = job_dir / ".scene_snapshot" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # Record the original snapshot manifest for comparison
        orig_manifest = list(manifest)
        entry0_source = Path(orig_manifest[0]["source"])

        # Change entry 0's source file so fingerprint differs, then re-randomize.
        # Patch random.choice so scene_folder_0 skips the original source (avoid flake).
        entry0_source.write_bytes(entry0_source.read_bytes() + b"extra")
        entry0_source.touch()

        import random as _random

        _orig_choice = _random.choice

        def _choice_skip_original(seq):
            candidates = [c for c in seq if str(c) != str(entry0_source)]
            return _orig_choice(candidates) if candidates else _orig_choice(seq)

        # Second run: should re-randomize only entry 0
        with patch("random.choice", _choice_skip_original), patches[0]:
            orch._run_scene_assembly(ctx)

        manifest2 = json.loads(manifest_path.read_text(encoding="utf-8"))

        # Entry 0 should have been re-randomized (different source file)
        assert manifest2[0]["source"] != manifest[0]["source"], (
            "Entry 0 should be re-randomized with a different source"
        )

        # Entries 1, 2 should be unchanged
        assert manifest2[1] == manifest[1], "Entry 1 should be unchanged"
        assert manifest2[2] == manifest[2], "Entry 2 should be unchanged"

    def test_force_reselect_still_works(self, tmp_path: Path):
        """force_reselect=True still causes a full re-randomize."""
        orch, ctx, root = self._setup_workspace(tmp_path, files_per_folder=5)
        job_dir = orch._job_dir(ctx)

        patches = [
            patch(
                "packages.pipeline_services.phase_orchestrator.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ),
        ]
        with patches[0]:
            orch._run_scene_assembly(ctx)

        manifest_path = job_dir / ".scene_snapshot" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        # force_reselect=True skips the manifest entirely
        ctx.options["force_reselect"] = True
        with patches[0]:
            orch._run_scene_assembly(ctx)

        manifest2 = json.loads(manifest_path.read_text(encoding="utf-8"))

        # All entries should be re-randomized (different from before)
        # Note: with random choice there's a tiny chance of picking the same file,
        # but the mtime will differ since we didn't touch the source
        assert manifest2 != manifest, "force_reselect should re-randomize all"
