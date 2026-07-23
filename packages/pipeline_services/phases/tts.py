"""TTS generation and review phase handlers."""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING, Any

from packages.domain_core.models import ExecutionFailure
from packages.domain_core.phase_execution import PhaseExecutionFailure
from packages.pipeline_services.force_align_service import (
    ForceAlignError,
    ForceAlignService,
)
from packages.pipeline_services.script_sentence import parse_script_sentences
from packages.pipeline_services.sentence_tts_service import SentenceTTSService

from .shared import _discover_script, _job_dir, _to_artifact

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """Execute per-sentence TTS synthesis or copy uploaded audio.

    Discovery order for uploaded audio:
        1. ``ctx.options["uploaded_audio_path"]`` → copy file, force-align,
           persist sentence timings, or raise ``ForceAlignError`` with
           per-sentence diagnostics.
        2. Otherwise discover script text from ``*口播文案.txt`` then ``*.json``
           and synthesize each canonical Script Sentence separately.
    """
    workspace_dir = ctx.root_dir / "workspace"
    job_dir = _job_dir(ctx)
    audio_path = job_dir / "audio.mp3"
    result: list = []
    uploaded_audio_path: str = ctx.options.get("uploaded_audio_path", "")

    # upload / library audio jobs do not need TTS synthesis (#249)
    audio_source: str = ctx.options.get("audio_source", "tts")
    if audio_source in ("upload", "library") and not uploaded_audio_path:
        print(
            f"[TTS] 跳过合成: audio_source={audio_source}, 无上传音频路径",
            flush=True,
        )
        return result

    if uploaded_audio_path:
        src_audio = ctx.root_dir / uploaded_audio_path
        if src_audio.exists():
            shutil.copy2(src_audio, audio_path)
            print(f"[TTS] Using uploaded audio: {src_audio}", flush=True)

            # Force-align uploaded audio to canonical Script Sentences
            existing_script = _discover_script(job_dir)
            if existing_script:
                sentences = parse_script_sentences(existing_script)
                if sentences:
                    align_svc = ForceAlignService()
                    align_result = align_svc.align(audio_path, sentences)

                    if align_result.status == "success":
                        sentences_path = job_dir / "sentences.json"
                        sentences_path.write_text(
                            json.dumps(
                                [t.model_dump() for t in align_result.timings],
                                ensure_ascii=False,
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                        result.append(
                            _to_artifact(
                                "sentence_timings",
                                sentences_path,
                                workspace_dir,
                            )
                        )
                        print(
                            f"[TTS] Force-aligned uploaded audio: "
                            f"{len(align_result.timings)} sentences, "
                            f"audio size={audio_path.stat().st_size}",
                            flush=True,
                        )
                    else:
                        # No fallback — surface per-sentence diagnostics
                        raise ForceAlignError(align_result)
                else:
                    print(
                        "[TTS] Uploaded audio: no parseable sentences in script",
                        flush=True,
                    )
            else:
                print(
                    f"[TTS] Uploaded audio: no script text found in {job_dir}",
                    flush=True,
                )
        else:
            print(f"[TTS WARN] Uploaded audio not found: {src_audio}", flush=True)
    else:
        existing_script = _discover_script(job_dir)
        print(
            f"[TTS DEBUG] phase=tts_generating, script_found={existing_script is not None}, "
            f"len={len(existing_script) if existing_script else 0}",
            flush=True,
        )
        if existing_script:
            tts_cfg = orchestrator._resolve_tts_config(ctx)

            # Apply job-level TTS overrides (tts_model / tts_voice)
            # Priority: job override > provider defaults > global/product config
            job_tts_model: str = ctx.options.get("tts_model", "")
            job_tts_voice: str = ctx.options.get("tts_voice", "")
            if job_tts_model:
                tts_cfg["model"] = job_tts_model
            if job_tts_voice:
                tts_cfg["voice"] = job_tts_voice

            # ponytail: only checks "cantonese", model-agnostic — Qwen uses
            # language_type, MiMo ignores it, so no model gate needed (#325)
            if ctx.options.get("language", "") == "cantonese":
                tts_cfg["language_type"] = "Chinese"

            tts_provider = orchestrator._build_tts_provider(tts_cfg)
            service = orchestrator._create_sentence_tts_service(
                tts_provider, tts_cfg, ctx
            )
            # Per-sentence retry is handled inside SentenceTTSService
            # (ADR 0005).  When all sentence-level retries are exhausted
            # the provider error propagates to execute_phase, which
            # classifies it as a structured PhaseExecutionFailure (#253).
            timings = service.synthesize_script(existing_script, audio_path)

            sentences_path = job_dir / "sentences.json"
            sentences_path.write_text(
                json.dumps(
                    [t.model_dump() for t in timings],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            result.append(
                _to_artifact("sentence_timings", sentences_path, workspace_dir)
            )
            print(
                f"[TTS] Synthesized: {audio_path.exists()}, "
                f"size={audio_path.stat().st_size if audio_path.exists() else 0}",
                flush=True,
            )
        else:
            print(f"[TTS WARN] No script text found in {job_dir}", flush=True)

    if audio_path.exists():
        result.append(_to_artifact("tts_audio", audio_path, workspace_dir))

    return result


def run_review(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """tts_review: return existing audio artifact for review."""
    job_dir = _job_dir(ctx)
    workspace_dir = ctx.root_dir / "workspace"
    audio_path = job_dir / "audio.mp3"
    if audio_path.exists():
        print(f"[TTS_REVIEW] Audio ready for review: {audio_path}", flush=True)
        return [_to_artifact("tts_audio", audio_path, workspace_dir)]
    print(f"[TTS_REVIEW WARN] No audio found in {job_dir}", flush=True)
    return []


def _create_sentence_tts_service(
    provider: Any, tts_cfg: dict[str, Any], ctx: PhaseContext
) -> SentenceTTSService:
    """Factory hook for the sentence-level TTS service (overridable in tests)."""
    cache_dir = ctx.root_dir / "workspace" / ".cache" / "tts"
    return SentenceTTSService(
        provider=provider,
        config=tts_cfg,
        cache_dir=cache_dir,
    )


def classify_tts_error(phase: str, exc: Exception) -> PhaseExecutionFailure:
    """Classify a TTS provider error into a structured failure (#253).

    Provider-specific error types are mapped to vendor-agnostic error codes
    so the frontend and retry policy never depend on provider internals.
    """
    from packages.pipeline_services.tts_provider import (
        TTSBlockedError,
        TTSQuotaExceededError,
        TTSRetriesExhaustedError,
        TTSRetryableError,
    )

    if isinstance(exc, TTSRetriesExhaustedError):
        return PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_RETRIES_EXHAUSTED",
                message=f"TTS 单句重试已耗尽: {exc.cause}",
                retryable=False,
            )
        )
    if isinstance(exc, TTSQuotaExceededError):
        return PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_QUOTA_EXCEEDED",
                message=f"TTS 配额超限，请稍后重试或更换模型: {exc}",
                retryable=True,
            )
        )
    if isinstance(exc, TTSBlockedError):
        return PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_PROVIDER_REJECTED",
                message=f"TTS 服务拒绝请求（鉴权失败或参数无效）: {exc}",
                retryable=False,
            )
        )
    if isinstance(exc, TTSRetryableError):
        return PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_SYNTHESIS_FAILED",
                message=f"TTS 合成失败（可重试）: {exc}",
                retryable=True,
            )
        )
    # Unknown / network errors are retryable
    return PhaseExecutionFailure(
        error=ExecutionFailure(
            code="TTS_SYNTHESIS_FAILED",
            message=f"TTS 合成失败: {exc}",
            retryable=True,
        )
    )
