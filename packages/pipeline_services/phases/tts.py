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
from packages.pipeline_services.logging_utils import get_pipeline_logger
from packages.pipeline_services.script_sentence import parse_script_sentences
from packages.pipeline_services.sentence_tts_service import SentenceTTSService

from .shared import _discover_script, _job_dir, _to_artifact

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )

_LOGGER = get_pipeline_logger(__name__)


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """Execute per-sentence TTS synthesis or copy uploaded audio.

    Discovery order for uploaded audio:
        1. ``ctx.options["uploaded_audio_path"]`` → copy file, force-align,
           persist sentence timings, or raise ``ForceAlignError`` with
           per-sentence diagnostics.
        2. Otherwise discover script text from ``*口播文案.txt`` then ``*.json``
           and synthesize each canonical Script Sentence separately.
    """
    job_dir = _job_dir(ctx)
    logger = _LOGGER.bind(ctx.job_id)
    audio_path = job_dir / "audio.mp3"
    result: list = []
    uploaded_audio_path: str = ctx.options.get("uploaded_audio_path", "")

    # upload / library audio jobs do not need TTS synthesis (#249)
    audio_source: str = ctx.options.get("audio_source", "tts")
    if audio_source in ("upload", "library") and not uploaded_audio_path:
        logger.info("[TTS] 跳过合成: audio_source=%s, 无上传音频路径", audio_source)
        return result

    if uploaded_audio_path:
        src_audio = ctx.root_dir / uploaded_audio_path
        if src_audio.exists():
            shutil.copy2(src_audio, audio_path)
            logger.info("[TTS] Using uploaded audio: %s", src_audio)

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
                                ctx.layout,
                            )
                        )
                        logger.info(
                            "[TTS] Force-aligned uploaded audio: %s sentences, "
                            "audio size=%s",
                            len(align_result.timings),
                            audio_path.stat().st_size,
                        )
                    else:
                        # No fallback — surface per-sentence diagnostics
                        raise ForceAlignError(align_result)
                else:
                    logger.warning(
                        "[TTS] Uploaded audio: no parseable sentences in script"
                    )
            else:
                logger.warning(
                    "[TTS] Uploaded audio: no script text found in %s", job_dir
                )
        else:
            logger.warning("[TTS WARN] Uploaded audio not found: %s", src_audio)
    else:
        existing_script = _discover_script(job_dir)
        logger.debug(
            "[TTS DEBUG] phase=tts_generating, script_found=%s, len=%s",
            existing_script is not None,
            len(existing_script) if existing_script else 0,
        )
        if existing_script:
            # Resolve via the single runtime entry point: raw dict + job-level
            # overrides (tts_model / tts_voice) -> TTSConfig, with provider
            # inferred from the final model.
            from packages.provider_config.tts_config import resolve_tts_config

            overrides: dict[str, Any] = {}
            job_tts_model: str = ctx.options.get("tts_model", "")
            job_tts_voice: str = ctx.options.get("tts_voice", "")
            if job_tts_model:
                overrides["model"] = job_tts_model
            if job_tts_voice:
                overrides["voice"] = job_tts_voice

            config = resolve_tts_config(
                dict(orchestrator._resolve_tts_config(ctx)), overrides
            )
            # Qwen uses language_type=Chinese for Cantonese; MiMo ignores it.
            if (
                ctx.options.get("language", "") == "cantonese"
                and config.provider == "qwen"
            ):
                config.language_type = "Chinese"
            tts_cfg = config.to_dict()

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
            result.append(_to_artifact("sentence_timings", sentences_path, ctx.layout))
            logger.info(
                "[TTS] Synthesized: %s, size=%s",
                audio_path.exists(),
                audio_path.stat().st_size if audio_path.exists() else 0,
            )
        else:
            logger.warning("[TTS WARN] No script text found in %s", job_dir)

    if audio_path.exists():
        result.append(_to_artifact("tts_audio", audio_path, ctx.layout))

    return result


def run_review(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """tts_review: return existing audio artifact for review."""
    job_dir = _job_dir(ctx)
    logger = _LOGGER.bind(ctx.job_id)
    audio_path = job_dir / "audio.mp3"
    if audio_path.exists():
        logger.info("[TTS_REVIEW] Audio ready for review: %s", audio_path)
        return [_to_artifact("tts_audio", audio_path, ctx.layout)]
    logger.warning("[TTS_REVIEW WARN] No audio found in %s", job_dir)
    return []


def _create_sentence_tts_service(
    provider: Any, tts_cfg: dict[str, Any], ctx: PhaseContext
) -> SentenceTTSService:
    """Factory hook for the sentence-level TTS service (overridable in tests)."""
    cache_dir = ctx.layout.workspace_url_prefix() / ".cache" / "tts"
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
