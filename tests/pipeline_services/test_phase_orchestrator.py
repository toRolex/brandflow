"""Tests for PhaseOrchestrator — script_generating migration (Slice 1)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from packages.domain_core.models import ArtifactPointer
from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
    PhaseOrchestrator,
    to_url_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """Create a minimal root_dir layout (workspace/projects/...)."""
    return tmp_path


@pytest.fixture()
def project_dir(tmp_root: Path) -> Path:
    d = tmp_root / "workspace" / "projects" / "proj-001"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def ctx(project_dir: Path, tmp_root: Path) -> PhaseContext:
    return PhaseContext(
        job_id="job-001",
        project_dir=project_dir,
        root_dir=tmp_root,
        product="羊肚菌",
        options={},
    )


@pytest.fixture()
def orchestrator() -> PhaseOrchestrator:
    bridge = MagicMock()
    subtitle_svc = MagicMock()
    video_svc = MagicMock()
    schedule_store = MagicMock()
    return PhaseOrchestrator(
        script_bridge=bridge,
        subtitle_svc=subtitle_svc,
        video_svc=video_svc,
        schedule_store=schedule_store,
    )


# ---------------------------------------------------------------------------
# PhaseContext
# ---------------------------------------------------------------------------


class TestPhaseContext:
    def test_fields(self, ctx: PhaseContext, project_dir: Path, tmp_root: Path):
        assert ctx.job_id == "job-001"
        assert ctx.project_dir == project_dir
        assert ctx.root_dir == tmp_root
        assert ctx.product == "羊肚菌"
        assert ctx.options == {}

    def test_options_carries_manual_script(self, project_dir: Path, tmp_root: Path):
        ctx = PhaseContext(
            job_id="j1",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            options={"manual_script": "手动文案"},
        )
        assert ctx.options["manual_script"] == "手动文案"


# ---------------------------------------------------------------------------
# to_url_path helper
# ---------------------------------------------------------------------------


class TestToUrlPath:
    def test_posix(self, tmp_path: Path):
        workspace = tmp_path / "workspace"
        file_path = (
            workspace / "projects" / "p" / "runtime" / "jobs" / "j1" / "口播文案.txt"
        )
        assert (
            to_url_path(file_path, workspace)
            == "projects/p/runtime/jobs/j1/口播文案.txt"
        )

    def test_slash_separated(self, tmp_path: Path):
        workspace = tmp_path / "workspace"
        file_path = workspace / "a" / "b" / "c.txt"
        assert to_url_path(file_path, workspace) == "a/b/c.txt"


# ---------------------------------------------------------------------------
# PhaseOrchestrator construction
# ---------------------------------------------------------------------------


class TestPhaseOrchestratorInit:
    def test_accepts_five_deps(self):
        orch = PhaseOrchestrator(
            script_bridge=MagicMock(),
            subtitle_svc=MagicMock(),
            video_svc=MagicMock(),
            schedule_store=MagicMock(),
        )
        assert orch._script_bridge is not None
        assert orch._subtitle_svc is not None
        assert orch._video_svc is not None
        assert orch._schedule_store is not None

    def test_has_handler_map(self):
        orch = PhaseOrchestrator(*[MagicMock()] * 4)
        assert isinstance(orch._handlers, dict)
        assert "script_generating" in orch._handlers


# ---------------------------------------------------------------------------
# run_phase dispatch
# ---------------------------------------------------------------------------


class TestRunPhase:
    def test_unknown_phase_raises(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        with pytest.raises(ValueError, match="Unknown phase"):
            orchestrator.run_phase("bogus_phase", ctx)

    def test_known_phase_returns_list(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """run_phase with script_generating should return a list (even if empty)."""
        result = orchestrator.run_phase("script_generating", ctx)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _run_script — manual_script path
# ---------------------------------------------------------------------------


class TestRunScriptManual:
    def test_manual_script_writes_files_and_returns_artifacts(
        self,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
    ):
        ctx.options["manual_script"] = "这是手动输入的文案内容。"

        artifacts = orchestrator.run_phase("script_generating", ctx)

        assert len(artifacts) == 2
        kinds = {a.kind for a in artifacts}
        assert kinds == {"script"}
        for a in artifacts:
            assert isinstance(a, ArtifactPointer)
            assert a.url.startswith("/workspace/")
            assert a.size_bytes > 0

        # Verify the files were written
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        txt_path = job_dir / "口播文案.txt"
        json_path = job_dir / "口播文案.json"
        assert txt_path.exists()
        assert txt_path.read_text(encoding="utf-8") == "这是手动输入的文案内容。"
        assert json_path.exists()
        jdata = json.loads(json_path.read_text(encoding="utf-8"))
        assert jdata["text"] == "这是手动输入的文案内容。"
        assert jdata["source"] == "manual"


# ---------------------------------------------------------------------------
# _run_script — LLM generation path
# ---------------------------------------------------------------------------


class TestRunScriptLLM:
    def test_llm_generation_calls_bridge_and_returns_artifacts(
        self,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
    ):
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        txt_path = job_dir / "口播文案.txt"
        json_path = job_dir / "口播文案.json"
        txt_path.write_text("LLM生成的文案", encoding="utf-8")
        json_path.write_text("{}", encoding="utf-8")

        orchestrator._script_bridge.generate.return_value = {
            "txt_path": str(txt_path),
            "json_path": str(json_path),
            "final_script": "LLM生成的文案",
        }

        artifacts = orchestrator.run_phase("script_generating", ctx)

        orchestrator._script_bridge.generate.assert_called_once_with(
            product="羊肚菌",
            output_dir=job_dir,
            mock=False,
            language="mandarin",
            brand="",
        )
        assert len(artifacts) == 2
        assert all(isinstance(a, ArtifactPointer) for a in artifacts)


# ---------------------------------------------------------------------------
# _run_script — cover title auto-generation
# ---------------------------------------------------------------------------


class TestRunScriptCoverTitle:
    @patch.object(PhaseOrchestrator, "_resolve_llm_config")
    @patch.object(PhaseOrchestrator, "_resolve_llm_api_key")
    @patch.object(PhaseOrchestrator, "_resolve_llm_endpoint")
    @patch("packages.pipeline_services.phase_orchestrator.ScriptGenerator")
    def test_auto_generates_cover_title_when_missing(
        self,
        mock_sg_cls: MagicMock,
        mock_endpoint: MagicMock,
        mock_api_key: MagicMock,
        mock_llm_config: MagicMock,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
    ):
        ctx.options["manual_script"] = "手动文案测试。"

        # Set up job JSON without cover_title
        job_json_dir = ctx.project_dir / "control" / "jobs"
        job_json_dir.mkdir(parents=True, exist_ok=True)
        job_json_path = job_json_dir / f"{ctx.job_id}.json"
        job_json_path.write_text(
            json.dumps(
                {"job_id": ctx.job_id, "phase": "script_generating"}, ensure_ascii=False
            ),
            encoding="utf-8",
        )

        mock_llm_config.return_value = {"model": "deepseek-v4-pro"}
        mock_api_key.return_value = "fake-api-key"
        mock_endpoint.return_value = "https://api.example.com"

        # Mock ScriptGenerator
        mock_gen = MagicMock()
        mock_sg_cls.return_value = mock_gen
        mock_gen.generate_cover_title.return_value = {
            "text": "羊肚菌美味",
            "highlight_words": ["羊肚菌"],
        }

        orchestrator.run_phase("script_generating", ctx)

        mock_gen.generate_cover_title.assert_called_once()
        # Verify job JSON was updated with cover_title
        updated = json.loads(job_json_path.read_text(encoding="utf-8"))
        assert updated["cover_title"]["text"] == "羊肚菌美味"

    @patch.object(PhaseOrchestrator, "_resolve_llm_config")
    @patch.object(PhaseOrchestrator, "_resolve_llm_api_key")
    @patch.object(PhaseOrchestrator, "_resolve_llm_endpoint")
    @patch("packages.pipeline_services.phase_orchestrator.ScriptGenerator")
    def test_skips_cover_title_when_already_set(
        self,
        mock_sg_cls: MagicMock,
        mock_endpoint: MagicMock,
        mock_api_key: MagicMock,
        mock_llm_config: MagicMock,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
    ):
        ctx.options["manual_script"] = "手动文案测试。"

        job_json_dir = ctx.project_dir / "control" / "jobs"
        job_json_dir.mkdir(parents=True, exist_ok=True)
        job_json_path = job_json_dir / f"{ctx.job_id}.json"
        job_json_path.write_text(
            json.dumps(
                {
                    "job_id": ctx.job_id,
                    "phase": "script_generating",
                    "cover_title": {"text": "已有标题"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        orchestrator.run_phase("script_generating", ctx)

        mock_sg_cls.assert_not_called()

    @patch.object(PhaseOrchestrator, "_resolve_llm_config")
    @patch.object(PhaseOrchestrator, "_resolve_llm_api_key")
    @patch.object(PhaseOrchestrator, "_resolve_llm_endpoint")
    @patch("packages.pipeline_services.phase_orchestrator.ScriptGenerator")
    def test_cover_title_error_does_not_propagate(
        self,
        mock_sg_cls: MagicMock,
        mock_endpoint: MagicMock,
        mock_api_key: MagicMock,
        mock_llm_config: MagicMock,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
        capsys: pytest.CaptureFixture,
    ):
        ctx.options["manual_script"] = "手动文案。"

        job_json_dir = ctx.project_dir / "control" / "jobs"
        job_json_dir.mkdir(parents=True, exist_ok=True)
        job_json_path = job_json_dir / f"{ctx.job_id}.json"
        job_json_path.write_text(
            json.dumps({"job_id": ctx.job_id}, ensure_ascii=False),
            encoding="utf-8",
        )

        mock_sg_cls.side_effect = RuntimeError("LLM down")

        # Should not raise
        artifacts = orchestrator.run_phase("script_generating", ctx)
        assert isinstance(artifacts, list)


# ---------------------------------------------------------------------------
# _job_dir helper
# ---------------------------------------------------------------------------


class TestJobDir:
    def test_returns_correct_path(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        expected = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        assert orchestrator._job_dir(ctx) == expected

    def test_creates_dir(self, orchestrator: PhaseOrchestrator, ctx: PhaseContext):
        d = orchestrator._job_dir(ctx)
        assert d.exists()


# ---------------------------------------------------------------------------
# _run_tts — TTS synthesis
# ---------------------------------------------------------------------------

_FAKE_TTS_CONFIG = {
    "model": "mimo-v2.5-tts",
    "voice": "Mia",
    "instructions": "",
    "language_type": "",
    "optimize_instructions": False,
    "fallback_voice": "Dean",
    "randomize_voice": False,
    "random_voices": ["Mia", "Dean"],
    "style_control_mode": "simple",
    "style_prompt": "自然 清晰",
    "voice_design_prompt": "",
    "audio_format": "wav",
    "audio_tags_enabled": False,
    "audio_tags": "",
    "voice_clone_sample_path": "",
    "voice_clone_mime_type": "",
    "optimize_text_preview": False,
    "director_character": "",
    "director_scene": "",
    "director_guidance": "",
}


def _make_orchestrator_with_tts_config(tts_provider=None, tts_config=None):
    """Build a PhaseOrchestrator with get_tts_config injected and _build_tts_provider mocked."""
    orch = PhaseOrchestrator(
        script_bridge=MagicMock(),
        subtitle_svc=MagicMock(),
        video_svc=MagicMock(),
        schedule_store=MagicMock(),
        get_tts_config=lambda: tts_config or dict(_FAKE_TTS_CONFIG),
    )
    mock_provider = tts_provider or MagicMock()
    orch._build_tts_provider = staticmethod(lambda cfg: mock_provider)
    return orch


class TestRunTTSScriptDiscovery:
    """_run_tts should discover script text from *口播文案.txt then *.json."""

    def test_reads_script_from_txt(self, tmp_path: Path, ctx: PhaseContext):
        """Given a 口播文案.txt file, _run_tts reads it and calls synthesize."""
        job_dir = (
            tmp_path
            / "workspace"
            / "projects"
            / "proj-001"
            / "runtime"
            / "jobs"
            / "job-001"
        )
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("这是一段测试文案。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"\x00" * 100
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        artifacts = orch.run_phase("tts_generating", ctx)

        mock_tts.synthesize.assert_called_once()
        call_args = mock_tts.synthesize.call_args
        assert call_args[0][0] == "这是一段测试文案。"
        assert len(artifacts) == 1
        assert artifacts[0].kind == "tts_audio"
        assert artifacts[0].size_bytes == 100

    def test_reads_script_from_json_when_no_txt(
        self, tmp_path: Path, ctx: PhaseContext
    ):
        """Falls back to 口播文案.json if no .txt file."""
        job_dir = (
            tmp_path
            / "workspace"
            / "projects"
            / "proj-001"
            / "runtime"
            / "jobs"
            / "job-001"
        )
        job_dir.mkdir(parents=True)
        jfile = job_dir / "口播文案.json"
        jfile.write_text(
            json.dumps({"text": "JSON 文案内容。"}, ensure_ascii=False),
            encoding="utf-8",
        )

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"\x00" * 50
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        orch.run_phase("tts_generating", ctx)

        mock_tts.synthesize.assert_called_once()
        assert mock_tts.synthesize.call_args[0][0] == "JSON 文案内容。"

    def test_no_script_produces_empty_artifacts(self, ctx: PhaseContext):
        """No script file → no synthesis, empty artifacts."""
        mock_tts = MagicMock()
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        artifacts = orch.run_phase("tts_generating", ctx)

        mock_tts.synthesize.assert_not_called()
        assert artifacts == []


class TestRunTTSUploadedAudio:
    """_run_tts should copy uploaded audio when uploaded_audio_path is set."""

    def test_copies_uploaded_audio(self, tmp_path: Path):
        """When uploaded_audio_path points to an existing file, copies it directly."""
        root_dir = tmp_path
        project_dir = tmp_path / "workspace" / "projects" / "proj-001"
        project_dir.mkdir(parents=True)

        # Create uploaded audio source
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        src = upload_dir / "sample.mp3"
        src.write_bytes(b"FAKE_AUDIO_DATA")

        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=root_dir,
            product="test",
            options={"uploaded_audio_path": str(src.relative_to(root_dir))},
        )

        mock_tts = MagicMock()
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        artifacts = orch.run_phase("tts_generating", ctx)

        mock_tts.synthesize.assert_not_called()
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        audio_path = job_dir / "audio.mp3"
        assert audio_path.exists()
        assert audio_path.read_bytes() == b"FAKE_AUDIO_DATA"
        assert len(artifacts) == 1
        assert artifacts[0].kind == "tts_audio"

    def test_missing_uploaded_audio_no_crash(self, tmp_path: Path, capsys):
        """When uploaded path doesn't exist, logs warning but doesn't crash."""
        root_dir = tmp_path
        project_dir = tmp_path / "workspace" / "projects" / "proj-001"
        project_dir.mkdir(parents=True)

        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=root_dir,
            product="test",
            options={"uploaded_audio_path": "nonexistent/file.mp3"},
        )

        mock_tts = MagicMock()
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        artifacts = orch.run_phase("tts_generating", ctx)

        mock_tts.synthesize.assert_not_called()
        assert artifacts == []


class TestRunTTSSynthesizeError:
    """TTS errors should be caught and logged, not propagated."""

    def test_synthesize_error_does_not_raise(self, ctx: PhaseContext, capsys):
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("测试文案。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.side_effect = RuntimeError("TTS service down")
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        # Should NOT raise
        artifacts = orch.run_phase("tts_generating", ctx)
        assert artifacts == []

        # Error was logged
        captured = capsys.readouterr()
        assert "TTS service down" in captured.out


class TestRunTTSConfigBuilding:
    """_run_tts builds a _TTSConfig shim from get_tts_config callable."""

    def test_passes_config_object_to_synthesize(self, ctx: PhaseContext):
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("测试。", encoding="utf-8")

        custom_config = dict(_FAKE_TTS_CONFIG)
        custom_config["voice"] = "Dean"
        custom_config["model"] = "mimo-v2-tts"

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"\x00"
        orch = _make_orchestrator_with_tts_config(
            tts_provider=mock_tts, tts_config=custom_config
        )

        orch.run_phase("tts_generating", ctx)

        call_args = mock_tts.synthesize.call_args
        config_obj = call_args[0][1]
        assert config_obj.voice == "Dean"
        assert config_obj.model == "mimo-v2-tts"


class TestRunTTSInHandlerMap:
    """tts_generating should be registered in the handler map."""

    def test_handler_registered(self):
        orch = _make_orchestrator_with_tts_config()
        assert "tts_generating" in orch._handlers


class TestRunTTSAudioWritten:
    """Audio file should be written to job_dir/audio.mp3."""

    def test_audio_written_to_job_dir(self, ctx: PhaseContext):
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("测试文案。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"\x01\x02\x03"
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        artifacts = orch.run_phase("tts_generating", ctx)

        audio_path = job_dir / "audio.mp3"
        assert audio_path.exists()
        assert audio_path.read_bytes() == b"\x01\x02\x03"
        assert len(artifacts) == 1
        assert artifacts[0].kind == "tts_audio"
        assert artifacts[0].url.startswith("/workspace/")
        assert artifacts[0].size_bytes == 3


# ---------------------------------------------------------------------------
# _run_video — import/generate mode base video composition
# ---------------------------------------------------------------------------


class TestRunVideo:
    """Import mode: _run_video now composes montage clips instead of
    short-circuiting on assembled.mp4."""

    def test_import_mode_concats_assembled_and_clips(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """Import mode: assembled.mp4 + selected_clips → built clip base + concat."""
        import subprocess
        from unittest.mock import patch

        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)

        # Create assembled.mp4 (scene segment from montage_assembling)
        (job_dir / "assembled.mp4").write_text("fake assembled video")

        # Create audio.mp3 and selected_clips.json (from tts + asset retrieval)
        (job_dir / "audio.mp3").write_text("fake audio")
        (job_dir / "selected_clips.json").write_text(
            json.dumps([{"file_path": str(job_dir / "clip1.mp4")}]),
            encoding="utf-8",
        )
        (job_dir / "clip1.mp4").write_text("fake clip")

        def _build_side_effect(*args, **kwargs):
            """Simulate VideoService.build_base_video producing _clip_base.mp4."""
            # args: (project_dir, job_dict, output_path)
            output_path = args[2]
            output_path.write_text("fake clip base video")

        orchestrator._video_svc.build_base_video.side_effect = _build_side_effect

        with patch.object(
            orchestrator, "_get_ffmpeg_path", return_value="ffmpeg"
        ):
            with patch.object(subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                def _concat_effect(*args, **kwargs):
                    """Simulate ffmpeg concat producing base.mp4."""
                    (job_dir / "base.mp4").write_text("concatenated video")
                    return MagicMock(returncode=0)

                mock_run.side_effect = _concat_effect

                artifacts = orchestrator.run_phase("video_rendering", ctx)

        assert len(artifacts) == 1
        assert artifacts[0].kind == "video_base"
        assert (job_dir / "base.mp4").exists()
        assert (job_dir / "base.mp4").read_text() == "concatenated video"

        # Verify build_base_video was called
        orchestrator._video_svc.build_base_video.assert_called_once()

        # Verify ffmpeg concat was called with both inputs
        concat_call = mock_run.call_args
        assert concat_call is not None
        call_args = concat_call[0][0]
        assert "-i" in call_args
        assert "-filter_complex" in call_args
        filter_idx = call_args.index("-filter_complex")
        filter_str = call_args[filter_idx + 1]
        assert "concat=n=2" in filter_str
        # Verify normalization: both inputs scaled to 720x1280@30fps yuv420p before concat
        assert "scale=720:1280" in filter_str
        assert "fps=30" in filter_str
        assert "format=pix_fmts=yuv420p" in filter_str
        assert "setsar=1" in filter_str

        # Temp _clip_base.mp4 should be cleaned up
        assert not (job_dir / "_clip_base.mp4").exists()

    def test_import_mode_fallback_no_clips(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """Import mode with assembled.mp4 but no clips → copy assembled as base."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)

        (job_dir / "assembled.mp4").write_text("fake assembled")
        # No audio.mp3, no selected_clips.json

        artifacts = orchestrator.run_phase("video_rendering", ctx)

        assert len(artifacts) == 1
        assert artifacts[0].kind == "video_base"
        assert (job_dir / "base.mp4").exists()
        assert (job_dir / "base.mp4").read_text() == "fake assembled"
        orchestrator._video_svc.build_base_video.assert_not_called()

    def test_generate_mode_clips_only(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """Generate mode: no assembled.mp4, build clip base directly."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)

        (job_dir / "audio.mp3").write_text("fake audio")
        (job_dir / "selected_clips.json").write_text(
            json.dumps([{"file_path": str(job_dir / "clip1.mp4")}]),
            encoding="utf-8",
        )
        (job_dir / "clip1.mp4").write_text("fake clip")

        def _build_side_effect(*args, **kwargs):
            output_path = args[2]
            output_path.write_text("clip base video")

        orchestrator._video_svc.build_base_video.side_effect = _build_side_effect

        artifacts = orchestrator.run_phase("video_rendering", ctx)

        assert len(artifacts) == 1
        assert artifacts[0].kind == "video_base"
        assert (job_dir / "base.mp4").exists()
        assert (job_dir / "base.mp4").read_text() == "clip base video"
        orchestrator._video_svc.build_base_video.assert_called_once()

    def test_no_sources_returns_empty(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """Neither assembled.mp4 nor clips available → empty artifacts."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)

        artifacts = orchestrator.run_phase("video_rendering", ctx)

        assert artifacts == []
        orchestrator._video_svc.build_base_video.assert_not_called()
