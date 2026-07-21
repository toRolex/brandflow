"""Config resolution helpers for phase handlers.

All functions accept the orchestrator instance so they can reach the injected
``ConfigReader`` / ``SecretStore`` without coupling handlers to construction
details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from packages.provider_config.config_constants import DEFAULTS

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


class _TTSConfigShim:
    """Duck-type config object built from the TTS config dict.

    Preserves the interface expected by ``tts_provider.synthesize()``.
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        defaults = DEFAULTS["tts"]
        director = defaults.get("director", {})
        audio_tags = defaults.get("audio_tags", {})

        self.model: str = cfg.get("model", defaults["model"])
        self.voice: str = cfg.get("voice", defaults["voice"])
        self.instructions: str = cfg.get("instructions", defaults["instructions"])
        self.language_type: str = cfg.get("language_type", defaults["language_type"])
        self.optimize_instructions: bool = cfg.get("optimize_instructions", False)
        self.fallback_voice: str = cfg.get("fallback_voice", defaults["fallback_voice"])
        self.randomize_voice: bool = cfg.get("randomize_voice", defaults["randomize_voice"])
        self.random_voices: list[str] = cfg.get(
            "random_voices", defaults["random_voices"]
        )
        self.style_control_mode: str = cfg.get(
            "style_control_mode", defaults["style_control_mode"]
        )
        self.style_prompt: str = cfg.get("style_prompt", defaults["style_prompt"])
        self.voice_design_prompt: str = cfg.get(
            "voice_design_prompt", defaults.get("voice_design_prompt", "")
        )
        self.audio_format: str = cfg.get("audio_format", defaults["audio_format"])
        self.audio_tags_enabled: bool = cfg.get(
            "audio_tags_enabled", audio_tags.get("enabled", False)
        )
        self.audio_tags: str = cfg.get("audio_tags", audio_tags.get("tags", ""))
        self.voice_clone_sample_path: str = cfg.get("voice_clone_sample_path", "")
        self.voice_clone_mime_type: str = cfg.get("voice_clone_mime_type", "")
        self.optimize_text_preview: bool = cfg.get("optimize_text_preview", False)
        self.director_character: str = cfg.get(
            "director_character", director.get("character", "")
        )
        self.director_scene: str = cfg.get(
            "director_scene", director.get("scene", "")
        )
        self.director_guidance: str = cfg.get(
            "director_guidance", director.get("guidance", "")
        )


def _resolve_tts_config(
    orchestrator: PhaseOrchestrator, ctx: PhaseContext
) -> dict[str, Any]:
    """Resolve TTS config via ConfigReader."""
    if orchestrator._config is not None:
        return orchestrator._config.get_tts_config(product_id=ctx.product)
    if orchestrator._get_tts_config is not None:
        return orchestrator._get_tts_config()
    raise RuntimeError(
        "No ConfigReader or TTS config callback available; "
        "create_orchestrator() requires a ConfigReader"
    )


def _resolve_llm_config(
    orchestrator: PhaseOrchestrator, ctx: PhaseContext
) -> dict[str, Any]:
    """Resolve LLM config via ConfigReader."""
    if orchestrator._config is not None:
        return orchestrator._config.get_llm_config(product_id=ctx.product)
    if orchestrator._get_llm_config is not None:
        return orchestrator._get_llm_config()
    raise RuntimeError(
        "No ConfigReader or LLM config callback available; "
        "create_orchestrator() requires a ConfigReader"
    )


def _resolve_api_key(
    orchestrator: PhaseOrchestrator, llm_config: dict[str, Any]
) -> str:
    """Resolve API key via SecretStore."""
    provider = llm_config.get("provider", "deepseek")
    return orchestrator._secrets.get_api_key(provider)


def _resolve_api_url(
    orchestrator: PhaseOrchestrator, llm_config: dict[str, Any]
) -> str:
    """Resolve API base URL via SecretStore."""
    provider = llm_config.get("provider", "deepseek")
    return orchestrator._secrets.get_api_base_url(provider)


def _resolve_categories(
    orchestrator: PhaseOrchestrator, ctx: PhaseContext
) -> list[str]:
    """Resolve category names for asset classification.

    Priority: product-level categories > asset_library categories > defaults.
    Uses ConfigReader when available; otherwise returns default food categories.
    """
    config_reader = orchestrator._config
    if config_reader is not None:
        product_config = config_reader.get_product_config(product_id=ctx.product)
        product_cats: list[dict] = product_config.get("categories", [])
        if product_cats:
            return [c.get("name", "") for c in product_cats if c.get("name")]

        al_config = config_reader.get_asset_library_config()
        raw: list[dict] = al_config.get("categories", [])
        if raw:
            return [c.get("name", "") for c in raw if c.get("name")]

    # Default food category names
    from packages.pipeline_services.asset_library.category_config import (
        default_categories,
    )

    return [c.name for c in default_categories()]


def _build_tts_provider(
    orchestrator: PhaseOrchestrator, tts_cfg: dict[str, Any]
) -> Any:
    """Build TTS provider dynamically from current config.

    Reads model from *tts_cfg* and returns the matching provider instance
    so that config changes (e.g. mimo to qwen) take effect immediately
    without restarting the worker.

    API keys are resolved via SecretStore.
    """
    from packages.pipeline_services.tts_provider import (
        MiMoTTSProvider,
        QwenTTSProvider,
    )

    tts_model = tts_cfg.get("model", DEFAULTS["tts"]["model"]) or ""

    if tts_model.startswith("qwen"):
        return QwenTTSProvider(
            api_key=orchestrator._secrets.get_api_key("qwen"),
            base_url=orchestrator._secrets.get_api_base_url("qwen")
            or "https://dashscope.aliyuncs.com/api/v1",
        )
    return MiMoTTSProvider(
        api_key=orchestrator._secrets.get_api_key("mimo"),
        base_url=orchestrator._secrets.get_api_base_url("mimo")
        or "https://api.xiaomimimo.com/v1",
    )
