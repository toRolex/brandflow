"""Tests for PhaseOrchestrator — script_generating migration (Slice 1)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from packages.domain_core.models import ArtifactPointer
from packages.domain_core.phase_execution import (
    PhaseExecutionFailure,
    PhaseExecutionSuccess,
)
from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
    PhaseOrchestrator,
    to_url_path,
)
from packages.pipeline_services.sentence_tts_service import SentenceTiming


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
    subtitle_svc = MagicMock()
    video_svc = MagicMock()
    schedule_store = MagicMock()
    return PhaseOrchestrator(
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
    def test_accepts_core_deps(self):
        orch = PhaseOrchestrator(
            subtitle_svc=MagicMock(),
            video_svc=MagicMock(),
            schedule_store=MagicMock(),
        )
        assert orch._subtitle_svc is not None
        assert orch._video_svc is not None
        assert orch._schedule_store is not None

    def test_has_handler_map(self):
        orch = PhaseOrchestrator(*[MagicMock()] * 2)
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
        ctx.options["manual_script"] = "测试文案"
        result = orchestrator.run_phase("script_generating", ctx)
        assert isinstance(result, list)

    def test_execute_phase_wraps_artifact_list(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        artifact = ArtifactPointer(kind="script", relative_path="script.json")
        orchestrator._handlers["legacy_phase"] = lambda _ctx: [artifact]

        result = orchestrator.execute_phase("legacy_phase", ctx)

        assert isinstance(result, PhaseExecutionSuccess)
        assert result.artifacts == [artifact]

    def test_run_phase_keeps_legacy_list_contract(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        artifact = ArtifactPointer(kind="script", relative_path="script.json")
        orchestrator._handlers["legacy_phase"] = lambda _ctx: [artifact]

        assert orchestrator.run_phase("legacy_phase", ctx) == [artifact]


class TestStructuredImportMediaResults:
    def test_missing_scene_inputs_is_deterministic_failure(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        result = orchestrator.execute_phase("scene_assembling", ctx)

        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "SCENE_INPUT_MISSING"
        assert result.error.retryable is False

    def test_missing_video_source_is_deterministic_failure(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        result = orchestrator.execute_phase("video_rendering", ctx)

        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "VIDEO_MONTAGE_SEGMENT_MISSING"
        assert result.error.retryable is False

    def test_media_timeout_is_retryable(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "montage_segment.mp4").write_bytes(b"source")
        orchestrator._handlers["video_rendering"] = MagicMock(
            side_effect=TimeoutError("ffmpeg timed out")
        )

        result = orchestrator.execute_phase("video_rendering", ctx)

        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "MEDIA_PROCESSING_TIMEOUT"
        assert result.error.retryable is True

    def test_empty_media_success_is_bounded_internal_failure(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "montage_segment.mp4").write_bytes(b"source")
        orchestrator._handlers["video_rendering"] = MagicMock(return_value=[])

        result = orchestrator.execute_phase("video_rendering", ctx)

        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "INTERNAL_EMPTY_RESULT"
        assert result.error.retryable is False


class TestExecutePhasesParallel:
    def _setup_tts_script(self, ctx: PhaseContext) -> None:
        """Ensure a script file exists so tts_generating validation passes."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "口播文案.txt").write_text("测试文案。", encoding="utf-8")

    def test_legacy_phase_crash_becomes_structured_failure(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """非结构化并行 phase 的异常不得转成空成功 sentinel。"""
        self._setup_tts_script(ctx)
        orchestrator._handlers["tts_generating"] = MagicMock(
            side_effect=RuntimeError("tts provider crashed")
        )

        results = orchestrator.execute_phases_parallel(["tts_generating"], ctx)

        result = results["tts_generating"]
        assert isinstance(result, PhaseExecutionFailure)
        # tts_generating is now structured (#253) — RuntimeError is classified
        # as TTS_SYNTHESIS_FAILED (retryable).
        assert result.error.code == "TTS_SYNTHESIS_FAILED"
        assert result.error.retryable is True

    def test_legacy_phase_empty_success_becomes_internal_failure(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """无产物成功在并行边界同样是有界内部错误。"""
        self._setup_tts_script(ctx)
        orchestrator._handlers["tts_generating"] = MagicMock(return_value=[])

        results = orchestrator.execute_phases_parallel(["tts_generating"], ctx)

        result = results["tts_generating"]
        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "INTERNAL_EMPTY_RESULT"
        assert result.error.retryable is False

    def test_successful_phases_pass_through(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        self._setup_tts_script(ctx)
        artifact = ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")
        orchestrator._handlers["tts_generating"] = MagicMock(return_value=[artifact])

        results = orchestrator.execute_phases_parallel(["tts_generating"], ctx)

        result = results["tts_generating"]
        assert isinstance(result, PhaseExecutionSuccess)
        assert result.artifacts == [artifact]


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
    @patch("packages.pipeline_services.phases.script.generate_script")
    def test_llm_generation_calls_script_generator_and_returns_artifacts(
        self,
        mock_generate_script: MagicMock,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
    ):
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        txt_path = job_dir / "口播文案.txt"
        json_path = job_dir / "口播文案.json"
        txt_path.write_text("LLM生成的文案", encoding="utf-8")
        json_path.write_text("{}", encoding="utf-8")

        mock_generate_script.return_value = {
            "txt_path": str(txt_path),
            "json_path": str(json_path),
            "final_script": "LLM生成的文案",
        }

        artifacts = orchestrator.run_phase("script_generating", ctx)

        mock_generate_script.assert_called_once()
        assert len(artifacts) == 2
        assert all(isinstance(a, ArtifactPointer) for a in artifacts)


# ---------------------------------------------------------------------------
# _run_script — cover title auto-generation
# ---------------------------------------------------------------------------


class TestRunScriptCoverTitle:
    @patch.object(PhaseOrchestrator, "_resolve_llm_config")
    @patch.object(PhaseOrchestrator, "_resolve_api_key")
    @patch.object(PhaseOrchestrator, "_resolve_api_url")
    @patch("packages.pipeline_services.phases.script.ScriptGenerator")
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
    @patch.object(PhaseOrchestrator, "_resolve_api_key")
    @patch.object(PhaseOrchestrator, "_resolve_api_url")
    @patch("packages.pipeline_services.phases.script.ScriptGenerator")
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
    @patch.object(PhaseOrchestrator, "_resolve_api_key")
    @patch.object(PhaseOrchestrator, "_resolve_api_url")
    @patch("packages.pipeline_services.phases.script.ScriptGenerator")
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


class _FakeSentenceTTSService:
    """Test double that simulates per-sentence synthesis without FFmpeg."""

    def __init__(self, provider: MagicMock, config: dict) -> None:
        self.provider = provider
        self.config = config

    def _config_shim(self):
        from packages.pipeline_services.tts_provider import TTSConfigShim

        return TTSConfigShim(self.config)

    def synthesize_script(
        self, script_text: str, output_path: Path
    ) -> list[SentenceTiming]:
        from packages.pipeline_services.script_sentence import parse_script_sentences

        sentences = parse_script_sentences(script_text)
        if not sentences:
            return []

        timings: list[SentenceTiming] = []
        start = 0.0
        audio_parts: list[bytes] = []
        for i, sentence in enumerate(sentences):
            shim = self._config_shim()
            audio_parts.append(self.provider.synthesize(sentence, shim))
            timings.append(
                SentenceTiming(
                    index=i,
                    text=sentence,
                    start_seconds=start,
                    end_seconds=start + 1.0,
                )
            )
            start += 1.0

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"".join(audio_parts))
        return timings


def _make_orchestrator_with_tts_config(tts_provider=None, tts_config=None):
    """Build a PhaseOrchestrator with get_tts_config injected and _build_tts_provider mocked."""
    orch = PhaseOrchestrator(
        subtitle_svc=MagicMock(),
        video_svc=MagicMock(),
        schedule_store=MagicMock(),
        get_tts_config=lambda: tts_config or dict(_FAKE_TTS_CONFIG),
    )
    mock_provider = tts_provider or MagicMock()
    orch._build_tts_provider = lambda cfg: mock_provider

    def _fake_service_factory(provider, cfg, _ctx):
        return _FakeSentenceTTSService(provider, cfg)

    orch._create_sentence_tts_service = _fake_service_factory
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
        assert len(artifacts) == 2
        kinds = {a.kind for a in artifacts}
        assert "tts_audio" in kinds
        assert "sentence_timings" in kinds
        audio_artifact = next(a for a in artifacts if a.kind == "tts_audio")
        assert audio_artifact.size_bytes == 100

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
    """TTS errors propagate to execute_phase for structured classification (#253)."""

    def test_synthesize_error_propagates_from_run_phase(self, ctx: PhaseContext):
        """TTS synthesis errors now propagate — caught by execute_phase wrapper."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("测试文案。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.side_effect = RuntimeError("TTS service down")
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        # run_phase will now propagate the error (no more silent catch)
        with pytest.raises(RuntimeError, match="TTS service down"):
            orch.run_phase("tts_generating", ctx)

    def test_synthesize_error_becomes_structured_failure_via_execute_phase(
        self, ctx: PhaseContext
    ):
        """execute_phase wraps TTS errors in PhaseExecutionFailure."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("测试文案。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.side_effect = RuntimeError("TTS service down")
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        # execute_phase catches the error and classifies it
        result = orch.execute_phase("tts_generating", ctx)
        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "TTS_SYNTHESIS_FAILED"
        assert result.error.retryable is True
        assert "TTS service down" in result.error.message


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

    def test_cantonese_sets_language_type_to_chinese(
        self, tmp_root: Path, project_dir: Path
    ):
        """language=cantonese 时 language_type 应为 Chinese. (#325)"""
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            options={"language": "cantonese"},
        )
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("测试。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"\x00"
        qwen_config = dict(_FAKE_TTS_CONFIG)
        qwen_config["model"] = "qwen-tts"
        orch = _make_orchestrator_with_tts_config(
            tts_provider=mock_tts, tts_config=qwen_config
        )

        orch.run_phase("tts_generating", ctx)

        call_args = mock_tts.synthesize.call_args
        config_obj = call_args[0][1]
        assert config_obj.language_type == "Chinese"

    def test_mandarin_does_not_force_language_type(
        self, tmp_root: Path, project_dir: Path
    ):
        """language=mandarin 时不强制 language_type. (#325)"""
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            options={"language": "mandarin"},
        )
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("测试。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"\x00"
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        orch.run_phase("tts_generating", ctx)

        call_args = mock_tts.synthesize.call_args
        config_obj = call_args[0][1]
        # _FAKE_TTS_CONFIG 中 language_type 为 ""，mandarin 不应改写
        assert config_obj.language_type == ""

    def test_no_language_does_not_force_language_type(
        self, tmp_root: Path, project_dir: Path
    ):
        """options 无 language 时不强制 language_type. (#325)"""
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            options={},
        )
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("测试。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"\x00"
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        orch.run_phase("tts_generating", ctx)

        call_args = mock_tts.synthesize.call_args
        config_obj = call_args[0][1]
        assert config_obj.language_type == ""


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
        assert len(artifacts) == 2
        kinds = {a.kind for a in artifacts}
        assert "tts_audio" in kinds
        assert "sentence_timings" in kinds


class TestRunTTSPerSentence:
    """Per-sentence TTS persists sentence timings alongside the audio file."""

    def test_per_sentence_tts_writes_audio_and_sentences_json(
        self, ctx: PhaseContext
    ) -> None:
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        txt = job_dir / "口播文案.txt"
        txt.write_text("第一句。第二句。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b"AUDIO"
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        artifacts = orch.run_phase("tts_generating", ctx)

        audio_path = job_dir / "audio.mp3"
        sentences_path = job_dir / "sentences.json"
        assert audio_path.exists()
        assert audio_path.read_bytes() == b"AUDIOAUDIO"
        assert sentences_path.exists()
        timings = json.loads(sentences_path.read_text(encoding="utf-8"))
        assert len(timings) == 2

        kinds = {a.kind for a in artifacts}
        assert "tts_audio" in kinds
        assert "sentence_timings" in kinds

    def test_run_tts_uses_same_config_for_all_sentences(
        self, ctx: PhaseContext
    ) -> None:
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "口播文案.txt").write_text("第一句。第二句。", encoding="utf-8")

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b""
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        orch.run_phase("tts_generating", ctx)

        voices = {call.args[1].voice for call in mock_tts.synthesize.call_args_list}
        models = {call.args[1].model for call in mock_tts.synthesize.call_args_list}
        assert len(voices) == 1
        assert len(models) == 1

    def test_run_tts_applies_job_level_overrides(self, ctx: PhaseContext) -> None:
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "口播文案.txt").write_text("第一句。", encoding="utf-8")
        ctx.options["tts_model"] = "qwen3-tts-flash"
        ctx.options["tts_voice"] = "Rocky"

        mock_tts = MagicMock()
        mock_tts.synthesize.return_value = b""
        orch = _make_orchestrator_with_tts_config(tts_provider=mock_tts)

        orch.run_phase("tts_generating", ctx)

        config_obj = mock_tts.synthesize.call_args.args[1]
        assert config_obj.model == "qwen3-tts-flash"
        assert config_obj.voice == "Rocky"


# ---------------------------------------------------------------------------
# _run_video — import/generate mode base video composition
# ---------------------------------------------------------------------------


class TestRunVideo:
    """video_rendering composes base.mp4 from the Montage Segment and an optional Scene Segment."""

    def test_no_montage_segment_returns_empty(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """Without a montage_segment.mp4 the handler cannot produce base.mp4."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)

        artifacts = orchestrator.run_phase("video_rendering", ctx)

        assert artifacts == []
        orchestrator._video_svc.build_base_video.assert_not_called()

    def test_copies_montage_when_no_scene(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """Generate mode: montage_segment.mp4 is used directly as base.mp4."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "montage_segment.mp4").write_text("montage video")
        (job_dir / "montage_segments.json").write_text(
            json.dumps([{"sentence": "s", "visual_type": "blank", "duration": 1.0}]),
            encoding="utf-8",
        )

        artifacts = orchestrator.run_phase("video_rendering", ctx)

        assert len(artifacts) == 1
        assert artifacts[0].kind == "video_base"
        assert (job_dir / "base.mp4").exists()
        assert (job_dir / "base.mp4").read_text() == "montage video"
        orchestrator._video_svc.build_base_video.assert_not_called()

    def test_concats_scene_and_montage(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """Import mode: scene_segment.mp4 + montage_segment.mp4 → base.mp4."""
        import subprocess
        from unittest.mock import patch

        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "scene_segment.mp4").write_text("fake scene")
        (job_dir / "montage_segment.mp4").write_text("fake montage")
        (job_dir / "montage_segments.json").write_text(
            json.dumps([{"sentence": "s", "visual_type": "blank", "duration": 1.0}]),
            encoding="utf-8",
        )

        with patch.object(orchestrator, "_get_ffmpeg_path", return_value="ffmpeg"):
            with patch.object(subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                def _concat_effect(*args, **kwargs):
                    (job_dir / "base.mp4").write_text("concatenated video")
                    return MagicMock(returncode=0)

                mock_run.side_effect = _concat_effect

                artifacts = orchestrator.run_phase("video_rendering", ctx)

        assert len(artifacts) == 1
        assert artifacts[0].kind == "video_base"
        assert (job_dir / "base.mp4").exists()
        assert (job_dir / "base.mp4").read_text() == "concatenated video"

        concat_call = mock_run.call_args
        assert concat_call is not None
        call_args = concat_call[0][0]
        assert "-filter_complex" in call_args
        filter_idx = call_args.index("-filter_complex")
        filter_str = call_args[filter_idx + 1]
        assert "concat=n=2" in filter_str
        assert "scale=720:1280" in filter_str

    def test_uses_montage_segments_for_final_timeline(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """The authoritative trim params are read from montage_segments.json."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "audio.mp3").write_bytes(b"fake audio")
        (job_dir / "montage_segment.mp4").write_text("fake montage")
        (job_dir / "montage_segments.json").write_text(
            json.dumps(
                [
                    {
                        "sentence": "第一句。",
                        "file_path": "",
                        "asset_id": "",
                        "visual_type": "blank",
                        "ss": 0.0,
                        "duration": 1.5,
                    }
                ]
            ),
            encoding="utf-8",
        )

        with patch.object(orchestrator, "_get_media_duration", return_value=1.5):
            orchestrator.run_phase("video_rendering", ctx)

        timeline_path = job_dir / "final_timeline.json"
        assert timeline_path.exists()
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        assert timeline["duration_ms"] == 1500


class TestFinalRendering:
    def test_unplayable_final_video_produces_no_artifact(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """A corrupt final.mp4 must keep the job out of the completed path."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "base.mp4").write_bytes(b"base")
        (job_dir / "audio.mp3").write_bytes(b"audio")
        (job_dir / "subtitles.srt").write_text("subtitle", encoding="utf-8")

        def write_corrupt_final(*_args, **_kwargs) -> None:
            (job_dir / "final.mp4").write_bytes(b"not a video")

        orchestrator._video_svc.burn_final_video.side_effect = write_corrupt_final

        with (
            patch(
                "packages.pipeline_services.phases.final_rendering.probe_media",
                return_value={
                    "duration": 1.0,
                    "video_codec": "h264",
                    "audio_codec": None,
                },
            ),
            patch(
                "packages.pipeline_services.phases.final_rendering.is_decodable_video",
                return_value=False,
            ),
        ):
            artifacts = orchestrator.run_phase("final_rendering", ctx)

        assert artifacts == []


class TestMontageAssembling:
    """montage_assembling builds the independent Montage Segment from the reviewed snapshot."""

    @pytest.fixture()
    def montage_job_dir(self, project_dir: Path) -> Path:
        d = project_dir / "runtime" / "jobs" / "job-001"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @pytest.fixture()
    def reviewed_snapshot(self, montage_job_dir: Path) -> Path:
        path = montage_job_dir / "reviewed_assets.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "sentence": "第一句。",
                        "file_path": "",
                        "asset_id": "",
                        "visual_type": "blank",
                        "duration": 1.5,
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    @pytest.fixture()
    def audio(self, montage_job_dir: Path) -> Path:
        path = montage_job_dir / "audio.mp3"
        path.write_bytes(b"fake audio")
        return path

    @pytest.fixture()
    def sentences(self, montage_job_dir: Path) -> Path:
        path = montage_job_dir / "sentences.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "index": 0,
                        "text": "第一句。",
                        "start_seconds": 0.0,
                        "end_seconds": 1.5,
                        "model": "mimo-v2.5-tts",
                        "voice": "Mia",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_validation_requires_snapshot(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        """No reviewed_assets.json → MONTAGE_SNAPSHOT_MISSING."""
        error = orchestrator.validate_phase_input("montage_assembling", ctx)
        assert error is not None
        assert error.code == "MONTAGE_SNAPSHOT_MISSING"

    def test_validation_requires_audio(
        self,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
        reviewed_snapshot: Path,
    ):
        error = orchestrator.validate_phase_input("montage_assembling", ctx)
        assert error is not None
        assert error.code == "MONTAGE_AUDIO_MISSING"

    def test_validation_requires_sentence_timings(
        self,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
        reviewed_snapshot: Path,
        audio: Path,
    ):
        error = orchestrator.validate_phase_input("montage_assembling", ctx)
        assert error is not None
        assert error.code == "MONTAGE_TIMINGS_MISSING"

    def test_validation_rejects_unresolved_decisions(
        self,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
        audio: Path,
        sentences: Path,
        montage_job_dir: Path,
    ):
        (montage_job_dir / "reviewed_assets.json").write_text(
            json.dumps(
                [
                    {
                        "sentence": "第一句。",
                        "file_path": "",
                        "asset_id": "",
                        "visual_type": "unresolved",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        error = orchestrator.validate_phase_input("montage_assembling", ctx)
        assert error is not None
        assert error.code == "MONTAGE_UNRESOLVED_DECISIONS"

    def test_validation_rejects_missing_clip_file(
        self,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
        audio: Path,
        sentences: Path,
        montage_job_dir: Path,
    ):
        (montage_job_dir / "reviewed_assets.json").write_text(
            json.dumps(
                [
                    {
                        "sentence": "第一句。",
                        "file_path": "/nonexistent/clip.mp4",
                        "asset_id": "clip-1",
                        "visual_type": "clip",
                        "duration": 1.5,
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        error = orchestrator.validate_phase_input("montage_assembling", ctx)
        assert error is not None
        assert error.code == "MONTAGE_CLIP_FILE_MISSING"

    def test_builds_montage_segment_and_segments_json(
        self,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
        reviewed_snapshot: Path,
        audio: Path,
        sentences: Path,
        montage_job_dir: Path,
    ):
        """Happy path: produces montage_segment.mp4 and montage_segments.json artifacts."""
        expected_trim = [
            {
                "sentence": "第一句。",
                "file_path": "",
                "asset_id": "",
                "visual_type": "blank",
                "ss": 0.0,
                "duration": 1.5,
            }
        ]

        def _build_side_effect(project_dir, job, output_path, sentence_timings=None):
            output_path.write_text("fake montage video")
            return expected_trim

        orchestrator._video_svc.build_base_video.side_effect = _build_side_effect

        artifacts = orchestrator.run_phase("montage_assembling", ctx)

        assert len(artifacts) == 2
        kinds = {a.kind for a in artifacts}
        assert kinds == {"montage_segment", "montage_segments"}
        assert (montage_job_dir / "montage_segment.mp4").exists()
        assert (montage_job_dir / "montage_segments.json").exists()
        assert (
            json.loads(
                (montage_job_dir / "montage_segments.json").read_text(encoding="utf-8")
            )
            == expected_trim
        )
        call_args = orchestrator._video_svc.build_base_video.call_args
        assert call_args[0][2] == montage_job_dir / "montage_segment.mp4"
        assert call_args[1]["sentence_timings"] == [
            {
                "index": 0,
                "text": "第一句。",
                "start_seconds": 0.0,
                "end_seconds": 1.5,
                "model": "mimo-v2.5-tts",
                "voice": "Mia",
            }
        ]

    def test_build_base_video_without_sentence_timings(
        self,
        orchestrator: PhaseOrchestrator,
        ctx: PhaseContext,
        reviewed_snapshot: Path,
        audio: Path,
        montage_job_dir: Path,
    ):
        """Legacy jobs without usable sentence timings still build the montage."""
        (montage_job_dir / "sentences.json").write_text(
            json.dumps([], ensure_ascii=False), encoding="utf-8"
        )

        def _build_side_effect(project_dir, job, output_path, sentence_timings=None):
            output_path.write_text("fake montage video")
            return []

        orchestrator._video_svc.build_base_video.side_effect = _build_side_effect

        artifacts = orchestrator.run_phase("montage_assembling", ctx)

        assert len(artifacts) == 2
        call_args = orchestrator._video_svc.build_base_video.call_args
        assert call_args[1]["sentence_timings"] is None


class TestMontageAssemblingEmptyResult:
    """When montage_assembling produces no artifacts, execute_phase reports a failure."""

    def test_empty_artifacts_are_structured_failure(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "reviewed_assets.json").write_text(
            json.dumps([{"sentence": "s", "visual_type": "blank", "duration": 1.0}]),
            encoding="utf-8",
        )
        (job_dir / "audio.mp3").write_bytes(b"fake audio")
        (job_dir / "sentences.json").write_text(
            json.dumps(
                [
                    {
                        "index": 0,
                        "text": "s",
                        "start_seconds": 0.0,
                        "end_seconds": 1.0,
                        "model": "",
                        "voice": "",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        orchestrator._video_svc.build_base_video.return_value = []

        result = orchestrator.execute_phase("montage_assembling", ctx)

        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "INTERNAL_EMPTY_RESULT"


class TestMontageRegression:
    """Issue #264: video_rendering must require the new Montage Segment, not legacy artifacts."""

    def test_video_rendering_no_longer_requires_assembled_mp4(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "assembled.mp4").write_text("legacy scene")
        (job_dir / "selected_clips.json").write_text("[]", encoding="utf-8")

        error = orchestrator.validate_phase_input("video_rendering", ctx)
        assert error is not None
        assert error.code == "VIDEO_MONTAGE_SEGMENT_MISSING"
        assert "assembled.mp4" not in error.message

    def test_video_rendering_accepts_montage_segment(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ):
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "montage_segment.mp4").write_text("montage")
        (job_dir / "montage_segments.json").write_text("[]", encoding="utf-8")

        assert orchestrator.validate_phase_input("video_rendering", ctx) is None


# ---------------------------------------------------------------------------
# TTS error classification (#253)
# ---------------------------------------------------------------------------


class TestTTSFailureClassification:
    """Provider-specific TTS errors map to vendor-agnostic execution failures."""

    def test_tts_quota_exceeded_is_retryable(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """TTSQuotaExceededError → retryable TTS_QUOTA_EXCEEDED."""
        from packages.pipeline_services.tts_provider import TTSQuotaExceededError

        result = orchestrator._classify_tts_error(
            "tts_generating", TTSQuotaExceededError("配额超限")
        )
        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "TTS_QUOTA_EXCEEDED"
        assert result.error.retryable is True

    def test_tts_blocked_error_is_non_retryable(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """TTSBlockedError → non-retryable TTS_PROVIDER_REJECTED."""
        from packages.pipeline_services.tts_provider import TTSBlockedError

        result = orchestrator._classify_tts_error(
            "tts_generating", TTSBlockedError("鉴权失败")
        )
        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "TTS_PROVIDER_REJECTED"
        assert result.error.retryable is False

    def test_tts_retryable_error_is_retryable(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """TTSRetryableError → retryable TTS_SYNTHESIS_FAILED."""
        from packages.pipeline_services.tts_provider import TTSRetryableError

        result = orchestrator._classify_tts_error(
            "tts_generating", TTSRetryableError("临时故障")
        )
        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "TTS_SYNTHESIS_FAILED"
        assert result.error.retryable is True

    def test_unknown_tts_error_is_retryable(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """Unknown/network errors → retryable TTS_SYNTHESIS_FAILED."""
        result = orchestrator._classify_tts_error(
            "tts_generating", ConnectionError("网络不可达")
        )
        assert isinstance(result, PhaseExecutionFailure)
        assert result.error.code == "TTS_SYNTHESIS_FAILED"
        assert result.error.retryable is True


class TestTTSValidation:
    """validate_phase_input for tts_generating."""

    def test_no_script_returns_validation_error(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """tts_generating without script → deterministic non-retryable error."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        # Ensure no script file exists
        for p in job_dir.glob("*口播文案*"):
            p.unlink()

        error = orchestrator.validate_phase_input("tts_generating", ctx)
        assert error is not None
        assert error.code == "TTS_SCRIPT_MISSING"
        assert error.retryable is False

    def test_validate_uploaded_audio_not_found(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """tts_generating with missing uploaded audio → deterministic error."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        # Write script so that check passes
        (job_dir / "口播文案.txt").write_text("测试文案", encoding="utf-8")
        ctx.options["uploaded_audio_path"] = "missing/audio.mp3"

        error = orchestrator.validate_phase_input("tts_generating", ctx)
        assert error is not None
        assert error.code == "UPLOAD_AUDIO_NOT_FOUND"
        assert error.retryable is False

    def test_script_exists_and_no_upload_audio_passes_validation(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """tts_generating with script and no upload → passes validation."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "口播文案.txt").write_text("测试文案", encoding="utf-8")

        error = orchestrator.validate_phase_input("tts_generating", ctx)
        assert error is None
