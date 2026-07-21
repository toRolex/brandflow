"""Phase handler sub-package for the pipeline orchestrator.

Each module exposes a single ``run(orchestrator, ctx)`` entry point that is
registered in ``PhaseOrchestrator._handlers``.  Shared stateless helpers and
config resolution utilities are also exported for convenience.
"""

from __future__ import annotations

from .asset import run as run_asset
from .config import (
    _TTSConfigShim,
    _build_tts_provider,
    _resolve_api_key,
    _resolve_api_url,
    _resolve_categories,
    _resolve_llm_config,
    _resolve_tts_config,
)
from .final_rendering import run as run_final_rendering
from .final_review import run as run_final_review
from .montage_assembly import load_montage_inputs, run as run_montage_assembly
from .scene_assembly import (
    _resolve_scene_folders,
    _scene_candidates,
    run as run_scene_assembly,
)
from .script import run as run_script
from .shared import (
    _discover_script,
    _discover_sentence_timings,
    _fallback_category_suggestion_model,
    _get_ffmpeg_path,
    _get_media_duration,
    _job_dir,
    _to_artifact,
    to_url_path,
)
from .subtitle import run as run_subtitle
from .tts import (
    _create_sentence_tts_service,
    classify_tts_error,
    run as run_tts,
    run_review as run_tts_review,
)
from .video_rendering import run as run_video_rendering

__all__ = [
    "run_asset",
    "run_final_rendering",
    "run_final_review",
    "run_montage_assembly",
    "run_scene_assembly",
    "run_script",
    "run_subtitle",
    "run_tts",
    "run_tts_review",
    "run_video_rendering",
    "load_montage_inputs",
    "_resolve_scene_folders",
    "_scene_candidates",
    "_TTSConfigShim",
    "_build_tts_provider",
    "_resolve_api_key",
    "_resolve_api_url",
    "_resolve_categories",
    "_resolve_llm_config",
    "_resolve_tts_config",
    "_discover_script",
    "_discover_sentence_timings",
    "_fallback_category_suggestion_model",
    "_get_ffmpeg_path",
    "_get_media_duration",
    "_job_dir",
    "_to_artifact",
    "to_url_path",
    "_create_sentence_tts_service",
    "classify_tts_error",
]
