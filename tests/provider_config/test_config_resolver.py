"""Tests for packages.provider_config.config_resolver."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.config_resolver import ConfigResolver
from packages.provider_config.secret_store import SecretStore


def _write_config(dir_path: str, data: dict) -> Path:
    config_path = Path(dir_path) / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return config_path


# ---------------------------------------------------------------------------
# tts()
# ---------------------------------------------------------------------------


class TestConfigResolverTTS:
    def test_tts_returns_defaults_when_empty_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            resolver = ConfigResolver(reader=reader)
            cfg = resolver.tts()
            assert cfg["provider"] == "qwen"
            assert cfg["model"] == "qwen-tts"

    def test_tts_applies_product_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "tts": {"voice": "RootVoice"},
                    "products": [
                        {"id": "snack", "tts": {"voice": "SnackVoice"}},
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            resolver = ConfigResolver(reader=reader)
            assert resolver.tts(product_id="snack")["voice"] == "SnackVoice"
            assert resolver.tts()["voice"] == "RootVoice"


# ---------------------------------------------------------------------------
# llm()
# ---------------------------------------------------------------------------


class TestConfigResolverLLM:
    def test_llm_returns_config_key_and_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            secrets = SecretStore(
                env={
                    "DEEPSEEK_API_KEY": "sk-deepseek",
                    "DEEPSEEK_API_URL": "https://api.deepseek.com/v1",
                }
            )
            resolver = ConfigResolver(reader=reader, secrets=secrets)
            cfg, api_key, api_url = resolver.llm()
            assert cfg["provider"] == "deepseek"
            assert api_key == "sk-deepseek"
            assert api_url == "https://api.deepseek.com/v1/chat/completions"

    def test_llm_appends_chat_completions_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            secrets = SecretStore(env={"DEEPSEEK_API_URL": "https://api.example.com/"})
            resolver = ConfigResolver(reader=reader, secrets=secrets)
            _, _, api_url = resolver.llm()
            assert api_url == "https://api.example.com/chat/completions"

    def test_llm_does_not_double_append_chat_completions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            secrets = SecretStore(
                env={"DEEPSEEK_API_URL": "https://api.example.com/chat/completions"}
            )
            resolver = ConfigResolver(reader=reader, secrets=secrets)
            _, _, api_url = resolver.llm()
            assert api_url == "https://api.example.com/chat/completions"

    def test_llm_empty_url_remains_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            secrets = SecretStore(env={})
            resolver = ConfigResolver(reader=reader, secrets=secrets)
            _, _, api_url = resolver.llm()
            assert api_url == ""

    def test_llm_uses_provider_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {"llm": {"provider": "kimi"}})
            reader = ConfigReader(config_dir=tmpdir)
            secrets = SecretStore(
                env={
                    "KIMI_API_KEY": "sk-kimi",
                    "KIMI_API_URL": "https://api.kimi.com",
                }
            )
            resolver = ConfigResolver(reader=reader, secrets=secrets)
            cfg, api_key, api_url = resolver.llm()
            assert cfg["provider"] == "kimi"
            assert api_key == "sk-kimi"
            assert api_url == "https://api.kimi.com/chat/completions"

    def test_llm_respects_product_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "llm": {"provider": "deepseek"},
                    "products": [
                        {
                            "id": "snack",
                            "llm": {"provider": "kimi"},
                        },
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            secrets = SecretStore(
                env={
                    "KIMI_API_KEY": "sk-kimi",
                    "KIMI_API_URL": "https://api.kimi.com",
                }
            )
            resolver = ConfigResolver(reader=reader, secrets=secrets)
            cfg, api_key, api_url = resolver.llm(product_id="snack")
            assert cfg["provider"] == "kimi"
            assert api_key == "sk-kimi"
            assert api_url == "https://api.kimi.com/chat/completions"


# ---------------------------------------------------------------------------
# categories()
# ---------------------------------------------------------------------------


class TestConfigResolverCategories:
    def test_categories_returns_default_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            resolver = ConfigResolver(reader=reader)
            names = resolver.categories()
            assert len(names) == 10
            assert names[0] == "产地溯源"
            assert names[-1] == "产品特写"

    def test_categories_returns_asset_library_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "asset_library": {
                        "categories": [
                            {"id": "harvest", "name": "采收采集"},
                            {"id": "processing", "name": "加工处理"},
                        ]
                    }
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            resolver = ConfigResolver(reader=reader)
            assert resolver.categories() == ["采收采集", "加工处理"]

    def test_categories_returns_product_level_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "products": [
                        {
                            "id": "snack",
                            "categories": [
                                {"id": "promo", "name": "促销活动"},
                            ],
                        }
                    ]
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            resolver = ConfigResolver(reader=reader)
            assert resolver.categories(product_id="snack") == ["促销活动"]

    def test_categories_skips_empty_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "asset_library": {
                        "categories": [
                            {"id": "valid", "name": "有效分类"},
                            {"id": "empty", "name": ""},
                        ]
                    }
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            resolver = ConfigResolver(reader=reader)
            assert resolver.categories() == ["有效分类"]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConfigResolverConstruction:
    def test_defaults_to_new_secret_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            resolver = ConfigResolver(reader=reader)
            assert resolver._secrets is not None

    def test_requires_reader(self) -> None:
        with pytest.raises(TypeError):
            ConfigResolver()  # type: ignore[call-arg]
