from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.pipeline_services.asset_library.category_config import (
    CategoryConfig,
    default_categories,
)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv: Any | None = None


DEFAULTS: dict[str, Any] = {
    "llm": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "thinking": "disabled",
    },
    "tts": {
        "provider": "qwen",
        "model": "qwen-tts",
        "voice": "Cherry",
        "fallback_voice": "Stella",
        "randomize_voice": True,
        "random_voices": ["Cherry", "Stella"],
        "style_prompt": "自然 清晰 适合短视频带货口播",
        "voice_design_prompt": "",
        "style_control_mode": "simple",
        "director": {
            "character": "",
            "scene": "",
            "guidance": "",
        },
        "audio_tags": {
            "enabled": False,
            "tags": "",
        },
        "audio_format": "wav",
        "sample_rate": None,
        "bitrate": None,
        "channel": None,
        "enable_request_logging": False,
        "enable_performance_metrics": True,
        "log_audio_duration": True,
    },
    "vision": {
        "provider": "xiaomi",
        "model": "mimo-v2.5",
    },
    "media": {
        "ffmpeg_path": "ffmpeg",
        "ffprobe_path": "ffprobe",
        "subtitle_mode": "script_timed",
        "max_retry": 3,
        "retry_delay_seconds": 60,
    },
    "asset_library": {
        "categories": [],
        "category_suggestion_model": "deepseek-v4-flash",
        "category_suggestion_sample_size": 20,
    },
    "video": {
        "cover_title_style": {
            "primary_color": "#FFD700",
            "outline_color": "#000000",
            "highlight_color": "#FF0000",
            "outline_width": 2.0,
            "position": "center",
        }
    },
    "scene": {
        "folders": [],
        "transition_duration_ms": 500,
    },
    "product": {
        "default_name": "",
        "default_brand": "",
        "script": {
            "scene": "",
            "material": "",
            "system_prompt": "你是一位短视频文案专家，撰写抖音口播文案。",
            "enable_qa_check": True,
            "word_count_min": 150,
            "word_count_max": 200,
            "max_sentence_length": 20,
            "forbidden_words": [
                "治疗", "治愈", "疗效", "降血糖", "降血压", "抗癌", "药到病除",
            ],
            "required_word_count": {
                "product": 1,
                "brand": 1,
            },
            "emoji_forbidden": True,
        },
        "categories": [],
        "keyword_map": {},
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深度合并两个字典，override 中的值覆盖 base 中的值，嵌套字典递归合并。"""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _get_nested(data: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """通过点分路径获取嵌套字典的值，如 'director.character'。"""
    keys = key_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _set_nested(data: dict[str, Any], key_path: str, value: Any) -> None:
    """通过点分路径设置嵌套字典的值，如 'director.character'。"""
    keys = key_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


class AppConfigManager:
    """统一配置管理器，读写 config/app_config.json"""

    API_KEY_ENV_MAP = {
        "mimo": "MIMO_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_API_KEY",
        "minimax": "MINIMAX_API_KEY",
    }

    API_BASE_URL_ENV_MAP = {
        "mimo": "MIMO_API_BASE_URL",
        "qwen": "DASHSCOPE_API_URL",
        "deepseek": "DEEPSEEK_API_URL",
        "kimi": "KIMI_API_URL",
        "minimax": "MINIMAX_TTS_URL",
    }

    VISION_API_KEY_ENV_MAP = {
        "xiaomi": "XIAOMI_VISION_API_KEY",
        "openai": "VISION_API_KEY",
        "claude": "VISION_API_KEY",
    }

    VISION_ENDPOINT_ENV_MAP = {
        "xiaomi": "XIAOMI_VISION_API_URL",
        "openai": "VISION_API_URL",
        "claude": "VISION_API_URL",
    }

    VISION_MODEL_ENV_MAP = {
        "xiaomi": "XIAOMI_VISION_MODEL",
        "openai": "VISION_MODEL",
        "claude": "VISION_MODEL",
    }

    def __init__(self, config_dir: str | Path = "config") -> None:
        if load_dotenv is not None:
            env_path = Path.cwd() / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=False)
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "app_config.json"

    def _load(self) -> dict[str, Any]:
        if self.config_path.exists():
            with open(self.config_path, encoding="utf-8") as f:
                raw = json.load(f)
            return self._migrate_if_needed(raw)
        return {}

    def _migrate_if_needed(self, raw: dict[str, Any]) -> dict[str, Any]:
        """自动迁移旧版 product 格式到新版 products 列表格式。"""
        if "product" in raw and "products" not in raw:
            old_product = raw.pop("product", {})
            raw["products"] = [
                {
                    "id": "default",
                    **old_product,
                }
            ]
            raw["active_product_id"] = "default"
            self._save(raw)
        return raw

    def _save(self, config: dict[str, Any]) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def _get_active_product_section(self, section: str) -> dict[str, Any]:
        """返回活跃产品中指定 section 的配置（如 tts/llm/vision），无则返回空 dict。"""
        raw = self._load()
        active_id = raw.get("active_product_id", "")
        if not active_id:
            return {}
        for p in raw.get("products", []):
            if p.get("id") == active_id:
                return p.get(section, {}) if isinstance(p.get(section), dict) else {}
        return {}

    def get_tts_config(self) -> dict[str, Any]:
        config = self._load()
        root_tts = config.get("tts", {})
        product_tts = self._get_active_product_section("tts")
        return _deep_merge(DEFAULTS["tts"], _deep_merge(root_tts, product_tts))

    def set_tts(self, key: str, value: Any) -> None:
        config = self._load()
        # 优先写入活跃产品的 product-level tts，与 get_tts_config() 读取路径一致
        active_id = config.get("active_product_id", "")
        if active_id:
            for i, p in enumerate(config.get("products", [])):
                if p.get("id") == active_id:
                    if "tts" not in p:
                        config["products"][i]["tts"] = {}
                    _set_nested(config["products"][i]["tts"], key, value)
                    self._save(config)
                    return
        if "tts" not in config:
            config["tts"] = {}
        _set_nested(config["tts"], key, value)
        self._save(config)

    def get_tts_value(self, key: str, default: Any = None) -> Any:
        config = self.get_tts_config()
        return _get_nested(config, key, default)

    def get_llm_config(self) -> dict[str, Any]:
        config = self._load()
        root_llm = config.get("llm", {})
        product_llm = self._get_active_product_section("llm")
        return _deep_merge(DEFAULTS["llm"], _deep_merge(root_llm, product_llm))

    def get_api_key(self, provider: str) -> str:
        import os

        # 优先读取 provider 专用 key，回退到通用 TTS_API_KEY 或 LLM_API_KEY
        env_key = self.API_KEY_ENV_MAP.get(provider, "")
        value = os.getenv(env_key, "").strip().strip('"').strip("'")
        if not value:
            # 根据 provider 类型回退到通用 key
            if provider in ("mimo", "minimax", "qwen"):
                value = os.getenv("TTS_API_KEY", "").strip().strip('"').strip("'")
            else:
                value = os.getenv("LLM_API_KEY", "").strip().strip('"').strip("'")
        return value

    def get_api_base_url(self, provider: str) -> str:
        import os

        # 优先读取 provider 专用 endpoint，回退到通用 TTS_API_URL 或 LLM_API_URL
        env_key = self.API_BASE_URL_ENV_MAP.get(provider, "")
        value = os.getenv(env_key, "").strip().rstrip("/")
        if not value:
            if provider in ("mimo", "minimax"):
                value = os.getenv("TTS_API_URL", "").strip().rstrip("/")
            elif provider != "qwen":
                value = os.getenv("LLM_API_URL", "").strip().rstrip("/")
        return value

    def get_llm_api_key(self) -> str:
        import os

        provider = self.get_llm_config().get("provider", "deepseek")
        # 优先读取 provider 专用 key，回退到通用 LLM_API_KEY
        env_key = self.API_KEY_ENV_MAP.get(provider, "")
        value = os.getenv(env_key, "").strip().strip('"').strip("'")
        if not value:
            value = os.getenv("LLM_API_KEY", "").strip().strip('"').strip("'")
        return value

    def get_llm_endpoint(self) -> str:
        import os

        provider = self.get_llm_config().get("provider", "deepseek")
        # 优先读取 provider 专用 endpoint，回退到通用 LLM_API_URL
        env_key = self.API_BASE_URL_ENV_MAP.get(provider, "")
        value = os.getenv(env_key, "").strip().rstrip("/")
        if not value:
            value = os.getenv("LLM_API_URL", "").strip().rstrip("/")
        return value

    def get_vision_config(self) -> dict[str, Any]:
        config = self._load()
        root_vision = config.get("vision", {})
        product_vision = self._get_active_product_section("vision")
        return _deep_merge(DEFAULTS["vision"], _deep_merge(root_vision, product_vision))

    def set_vision(self, key: str, value: Any) -> None:
        config = self._load()
        # 优先写入活跃产品的 product-level vision，与 get_vision_config() 读取路径一致
        active_id = config.get("active_product_id", "")
        if active_id:
            for i, p in enumerate(config.get("products", [])):
                if p.get("id") == active_id:
                    if "vision" not in p:
                        config["products"][i]["vision"] = {}
                    _set_nested(config["products"][i]["vision"], key, value)
                    self._save(config)
                    return
        if "vision" not in config:
            config["vision"] = {}
        _set_nested(config["vision"], key, value)
        self._save(config)

    def get_vision_api_key(self) -> str:
        import os

        provider = self.get_vision_config().get("provider", "xiaomi")
        # 优先读取 provider 专用 key，回退到通用 VISION_API_KEY
        env_key = self.VISION_API_KEY_ENV_MAP.get(provider, "VISION_API_KEY")
        value = os.getenv(env_key, "").strip().strip('"').strip("'")
        if not value:
            value = os.getenv("VISION_API_KEY", "").strip().strip('"').strip("'")
        return value

    def get_vision_endpoint(self) -> str:
        import os

        provider = self.get_vision_config().get("provider", "xiaomi")
        # 优先读取 provider 专用 endpoint，回退到通用 VISION_API_URL
        env_key = self.VISION_ENDPOINT_ENV_MAP.get(provider, "VISION_API_URL")
        value = os.getenv(env_key, "").strip().rstrip("/")
        if not value:
            value = os.getenv("VISION_API_URL", "").strip().rstrip("/")
        return value

    def get_vision_model(self) -> str:
        import os

        provider = self.get_vision_config().get("provider", "xiaomi")
        # 优先读取 provider 专用 model，回退到通用 VISION_MODEL
        env_key = self.VISION_MODEL_ENV_MAP.get(provider, "VISION_MODEL")
        value = os.getenv(env_key, "").strip()
        if not value:
            value = os.getenv("VISION_MODEL", "").strip()
        return value

    def get_media_config(self) -> dict[str, Any]:
        config = self._load()
        media = config.get("media", {})
        defaults = DEFAULTS["media"]
        return _deep_merge(defaults, media)

    def get_video_config(self) -> dict[str, Any]:
        config = self._load()
        video = config.get("video", {})
        defaults = DEFAULTS["video"]
        return _deep_merge(defaults, video)

    def set_video(self, key: str, value: Any) -> None:
        config = self._load()
        if "video" not in config:
            config["video"] = {}
        _set_nested(config["video"], key, value)
        self._save(config)

    def get_video_value(self, key: str, default: Any = None) -> Any:
        config = self.get_video_config()
        return _get_nested(config, key, default)

    def get_scene_config(self) -> dict[str, Any]:
        """Return scene config, preferring product-level overrides.

        Priority chain:
        1. ``product.scene`` (active product-level override)
        2. ``scene`` (top-level, backward compatible)
        3. ``DEFAULTS["scene"]``
        """
        defaults = DEFAULTS["scene"]

        # Priority 1: product-level scene config
        product_config = self.get_product_config()
        scene = product_config.get("scene")
        if isinstance(scene, dict) and scene:
            return _deep_merge(defaults, scene)

        # Priority 2: top-level scene config (backward compatible)
        config = self._load()
        scene = config.get("scene", {})
        return _deep_merge(defaults, scene)

    def get_product_config(self, product_id: str | None = None) -> dict[str, Any]:
        """获取产品配置。

        Args:
            product_id: 指定产品 ID。为 None 时返回活跃产品配置。
        """
        raw = self._load()
        defaults = DEFAULTS["product"]
        products = raw.get("products", [])

        if product_id:
            # 查找指定产品
            for p in products:
                if p.get("id") == product_id:
                    merged = _deep_merge(defaults, p)
                    merged.setdefault("id", product_id)
                    if not merged.get("name"):
                        merged["name"] = merged.get("default_name", "") or merged.get("id", "")
                    return merged
            merged = deepcopy(defaults)
            merged["id"] = product_id
            merged["name"] = ""
            return merged

        # 无参时返回活跃产品配置
        if not products:
            return deepcopy(defaults)

        active_id = raw.get("active_product_id", "")
        for p in products:
            if p.get("id") == active_id:
                merged = _deep_merge(defaults, p)
                merged.setdefault("id", active_id)
                if not merged.get("name"):
                    merged["name"] = merged.get("default_name", "") or merged.get("id", "")
                return merged

        # 活跃产品未找到时返回 DEFAULTS
        return deepcopy(defaults)

    def set_product_config(self, values: dict[str, Any]) -> None:
        raw = self._load()
        self._ensure_active_product(raw)
        active_id = raw.get("active_product_id", "")

        for i, p in enumerate(raw["products"]):
            if p.get("id") == active_id:
                existing = raw["products"][i]
                merged = _deep_merge(existing, values)
                merged.pop("name", None)
                raw["products"][i] = merged
                break

        self._save(raw)

    def save_product_config(self, product_id: str, values: dict[str, Any]) -> None:
        """保存指定产品的完整配置，不切换活跃产品。"""
        raw = self._load()
        self._ensure_active_product(raw)

        for i, p in enumerate(raw["products"]):
            if p.get("id") == product_id:
                existing = raw["products"][i]
                merged = _deep_merge(existing, values)
                merged["id"] = product_id
                merged.pop("name", None)
                raw["products"][i] = merged
                self._save(raw)
                return

        # 产品不存在时创建它
        raw["products"].append({"id": product_id, **values})
        self._save(raw)

    def set_product(self, key: str, value: Any) -> None:
        raw = self._load()
        self._ensure_active_product(raw)
        active_id = raw.get("active_product_id", "")

        for i, p in enumerate(raw["products"]):
            if p.get("id") == active_id:
                _set_nested(raw["products"][i], key, value)
                break

        self._save(raw)

    def reset_product_config(self) -> None:
        raw = self._load()
        active_id = raw.get("active_product_id", "")

        # 移除活跃产品
        products = raw.get("products", [])
        for i, p in enumerate(products):
            if p.get("id") == active_id:
                products.pop(i)
                break

        # 重置活跃索引
        if products:
            raw["active_product_id"] = products[0]["id"]
        else:
            raw["active_product_id"] = ""

        self._save(raw)

    def get_product_value(self, key: str, default: Any = None) -> Any:
        config = self.get_product_config()
        return _get_nested(config, key, default)

    def _ensure_active_product(self, raw: dict[str, Any]) -> dict[str, Any]:
        """确保 products 列表和活跃产品存在，用于写入操作。"""
        if "products" not in raw:
            raw["products"] = []
        if "active_product_id" not in raw:
            raw["active_product_id"] = ""

        # 有产品但无活跃 ID 时选择第一个
        if not raw["active_product_id"] and raw["products"]:
            raw["active_product_id"] = raw["products"][0]["id"]

        # 无任何产品时创建默认
        if not raw["products"]:
            raw["products"] = [{"id": "default"}]
            raw["active_product_id"] = "default"

        return raw

    def create_product(self, name: str) -> dict[str, str]:
        """创建新产品。name 同时作为产品 ID，不可为空。"""
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("product name cannot be empty")

        raw = self._load()
        if "products" not in raw:
            raw["products"] = []

        # 产品已存在时直接返回
        for p in raw["products"]:
            if p.get("id") == trimmed:
                return {"id": trimmed, "name": trimmed}

        raw["products"].append({"id": trimmed, "default_name": trimmed})
        if "active_product_id" not in raw or not raw["active_product_id"]:
            raw["active_product_id"] = trimmed

        self._save(raw)
        return {"id": trimmed, "name": trimmed}

    def rename_product(self, product_id: str, name: str) -> dict[str, str]:
        """重命名产品。只改变显示名称，不改变产品 ID。"""
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("product name cannot be empty")

        raw = self._load()
        for i, p in enumerate(raw.get("products", [])):
            if p.get("id") == product_id:
                raw["products"][i]["default_name"] = trimmed
                self._save(raw)
                return {"id": product_id, "name": trimmed}

        raise ValueError("product not found")

    def delete_product(self, product_id: str) -> dict[str, str | None]:
        """删除产品。删除活跃产品时自动选择第一个剩余产品。"""
        raw = self._load()
        products = raw.get("products", [])

        # 查找要删除的产品
        index = None
        for i, p in enumerate(products):
            if p.get("id") == product_id:
                index = i
                break

        if index is None:
            raise ValueError("product not found")

        was_active = raw.get("active_product_id") == product_id
        products.pop(index)

        # 如果删除的是活跃产品，重置活跃产品
        new_active = raw.get("active_product_id")
        if was_active:
            if products:
                new_active = products[0]["id"]
            else:
                new_active = ""
            raw["active_product_id"] = new_active

        self._save(raw)
        return {"status": "deleted", "active_product_id": new_active}

    def switch_product(self, product_id: str) -> None:
        """切换到指定产品，不存在时自动创建。"""
        raw = self._load()
        if "products" not in raw:
            raw["products"] = []

        found = any(p.get("id") == product_id for p in raw["products"])
        if not found:
            raw["products"].append({"id": product_id})

        raw["active_product_id"] = product_id
        self._save(raw)

    def list_products(self) -> list[dict[str, str]]:
        """返回所有产品的 id + name 摘要。"""
        raw = self._load()
        products = raw.get("products", [])
        return [
            {
                "id": p.get("id", ""),
                "name": p.get("default_name", "") or p.get("name", "") or p.get("id", ""),
            }
            for p in products
        ]

    def resolve_product_name(self, explicit_product: str = "") -> str:
        """Resolve product name with fallback chain.

        Priority: explicit_product > active product name > default_name > id.
        Returns empty string when no active product is configured.
        """
        if explicit_product:
            return explicit_product
        config = self.get_product_config()
        name = config.get("name", "")
        if name:
            return name
        default = config.get("default_name", "")
        if default:
            return default
        return config.get("id", "")

    def get_asset_library_config(self) -> dict[str, Any]:
        config = self._load()
        al = config.get("asset_library", {})
        defaults = DEFAULTS["asset_library"]
        return _deep_merge(defaults, al)

    def get_categories(self) -> list[CategoryConfig]:
        """Return the configured asset categories.

        Priority chain:
        1. ``product.categories`` (product-level override)
        2. ``asset_library.categories`` (instance-level, backward compatible)
        3. ``default_categories()`` (food fallback)
        """
        # Priority 1: product-level categories
        product_config = self.get_product_config()
        product_cats: list[dict] = product_config.get("categories", [])
        if product_cats:
            return [
                CategoryConfig(
                    id=c.get("id", ""),
                    name=c.get("name", ""),
                    description=c.get("description", ""),
                    vision_prompt=c.get("vision_prompt", ""),
                )
                for c in product_cats
            ]

        # Priority 2: asset_library categories (backward compatible)
        al_config = self.get_asset_library_config()
        raw: list[dict] = al_config.get("categories", [])
        if raw:
            return [
                CategoryConfig(
                    id=c.get("id", ""),
                    name=c.get("name", ""),
                    description=c.get("description", ""),
                    vision_prompt=c.get("vision_prompt", ""),
                )
                for c in raw
            ]

        # Priority 3: default food categories
        return default_categories()

    def get_keyword_map(self) -> dict[str, list[str]]:
        """Return the keyword-to-category mapping for the active product.

        Reads from the product-level ``keyword_map`` field.  Returns an empty
        mapping when the product has not configured one — no hardcoded fallback.
        """
        product_config = self.get_product_config()
        raw: dict = product_config.get("keyword_map", {})
        if not isinstance(raw, dict):
            return {}
        return {str(k): list(v) for k, v in raw.items() if isinstance(v, list)}

    def get_category_suggestion_model(self) -> str:
        al_config = self.get_asset_library_config()
        return al_config.get("category_suggestion_model", "deepseek-v4-flash")

    def get_category_suggestion_sample_size(self) -> int:
        al_config = self.get_asset_library_config()
        return al_config.get("category_suggestion_sample_size", 20)
