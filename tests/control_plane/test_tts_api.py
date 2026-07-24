from pathlib import Path

import base64
import io
import wave
from collections.abc import Callable

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app
from packages.provider_config.tts_config import TTSConfig


@pytest.fixture(autouse=True)
def _cleanup_tts_config():
    """Save and restore config/app_config.json so TTS config PUTs don't leak across tests."""
    config_file = Path("config/app_config.json")
    original = None
    if config_file.exists():
        original = config_file.read_text(encoding="utf-8")
    yield
    if original is not None:
        config_file.write_text(original, encoding="utf-8")
    elif config_file.exists():
        config_file.unlink()


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestTTSConfigAPI:
    def test_get_config_default(self, client):
        response = client.get("/api/tts/config")
        assert response.status_code == 200
        data = response.json()
        assert "model" in data
        assert "voice" in data

    def test_save_config(self, client):
        config = {
            "model": "mimo-v2.5-tts-voicedesign",
            "voice_design_prompt": "年轻女性，声音甜美",
            "style_prompt": "活泼热情",
        }
        response = client.put("/api/tts/config", json=config)
        assert response.status_code == 200
        assert response.json()["success"] is True

        # roundtrip: verify saved config is retrievable
        loaded = client.get("/api/tts/config").json()
        for key, value in config.items():
            assert loaded[key] == value

    def test_save_config_with_partial_fields(self, client):
        response = client.put("/api/tts/config", json={"model": "custom-model"})
        assert response.status_code == 200

        loaded = client.get("/api/tts/config").json()
        assert loaded["model"] == "custom-model"

    def test_get_voices_default(self, client):
        response = client.get("/api/tts/voices")
        assert response.status_code == 200
        data = response.json()
        assert "preset_voices" in data
        assert len(data["preset_voices"]) > 0

    def test_get_voices_with_model_mimo(self, client):
        response = client.get("/api/tts/voices?model=mimo-v2.5-tts")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        assert len(voices) > 0
        assert all(v["model"] == "mimo-v2.5-tts" for v in voices)

    def test_get_voices_with_model_qwen_instruct(self, client):
        """model=qwen3-tts-instruct-flash 应排除 INSTRUCT_UNSUPPORTED_VOICES"""
        response = client.get("/api/tts/voices?model=qwen3-tts-instruct-flash")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        ids = {v["id"] for v in voices}
        assert "Jennifer" not in ids
        assert "Ryan" not in ids
        assert "Katerina" not in ids
        assert "Rocky" in ids  # a supported voice is still there

    def test_get_voices_with_model_qwen_flash(self, client):
        """model=qwen3-tts-flash 应返回完整音色列表（含 3 个不支持 instruct 的音色）"""
        response = client.get("/api/tts/voices?model=qwen3-tts-flash")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        ids = {v["id"] for v in voices}
        assert "Jennifer" in ids
        assert "Ryan" in ids
        assert "Katerina" in ids

    def test_get_voices_unknown_model_returns_400(self, client):
        response = client.get("/api/tts/voices?model=unknown-model")
        assert response.status_code == 400

    def test_get_voices_with_provider_mimo(self, client):
        """backward compat: ?provider=mimo 仍有效"""
        response = client.get("/api/tts/voices?provider=mimo")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        assert all(v["model"] == "mimo-v2.5-tts" for v in voices)

    def test_get_voices_with_provider_qwen(self, client):
        """backward compat: ?provider=qwen 仍有效"""
        response = client.get("/api/tts/voices?provider=qwen")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        assert all(v["model"].startswith("qwen") for v in voices)

    def test_get_voices_unknown_provider_returns_400(self, client):
        """backward compat: 未知 provider 仍返回 400"""
        response = client.get("/api/tts/voices?provider=unknown")
        assert response.status_code == 400

    # ── voice/model 归属校验 (#222) ──────────────────────────────────

    def test_save_config_mimo_model_qwen_voice_returns_422(self, client):
        """MiMo 模型 + Qwen 音色 'Rocky' → 422"""
        response = client.put(
            "/api/tts/config",
            json={"model": "mimo-v2.5-tts", "voice": "Rocky"},
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Rocky" in detail
        assert "Mia" in detail or "mimo-v2.5-tts" in detail

    def test_save_config_voicedesign_model_any_voice_passes(self, client):
        """voicedesign 模型发送 Qwen 音色 → 正常，不触发校验"""
        response = client.put(
            "/api/tts/config",
            json={
                "model": "mimo-v2.5-tts-voicedesign",
                "voice": "Rocky",
                "voice_design_prompt": "年轻女性",
            },
        )
        assert response.status_code == 200

    def test_save_config_voiceclone_model_any_voice_passes(self, client):
        """voiceclone 模型发送 Qwen 音色 → 正常，不触发校验"""
        response = client.put(
            "/api/tts/config",
            json={"model": "mimo-v2.5-tts-voiceclone", "voice": "Rocky"},
        )
        assert response.status_code == 200

    def test_save_config_voicedesign_empty_voice_passes(self, client):
        """voicedesign 模型空 voice → 正常"""
        response = client.put(
            "/api/tts/config",
            json={
                "model": "mimo-v2.5-tts-voicedesign",
                "voice": "",
                "voice_design_prompt": "年轻女性",
            },
        )
        assert response.status_code == 200

    def test_save_config_valid_mimo_voice_passes(self, client):
        """有效 MiMo voice/model 组合正常保存"""
        response = client.put(
            "/api/tts/config",
            json={"model": "mimo-v2.5-tts", "voice": "Mia"},
        )
        assert response.status_code == 200

    def test_save_config_valid_qwen_voice_passes(self, client):
        """有效 Qwen voice/model 组合正常保存"""
        response = client.put(
            "/api/tts/config",
            json={"model": "qwen3-tts-instruct-flash", "voice": "Rocky"},
        )
        assert response.status_code == 200

    def test_save_config_qwen_flash_any_voice_passes(self, client):
        """qwen3-tts-flash 支持全量 35 个音色（含 Jennifer）"""
        response = client.put(
            "/api/tts/config",
            json={"model": "qwen3-tts-flash", "voice": "Jennifer"},
        )
        assert response.status_code == 200

    def test_save_config_instruct_with_unsupported_voice_returns_422(self, client):
        """qwen3-tts-instruct-flash + Jennifer（instruct 不支持的音色）→ 422"""
        response = client.put(
            "/api/tts/config",
            json={"model": "qwen3-tts-instruct-flash", "voice": "Jennifer"},
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Jennifer" in detail
        assert "qwen3-tts-instruct-flash" in detail


class TestTTSPreviewAPI:
    def test_preview_requires_text(self, client):
        response = client.post("/api/tts/preview", json={})
        assert response.status_code == 422

    def test_preview_with_valid_text(self, client):
        response = client.post(
            "/api/tts/preview",
            json={
                "text": "测试文本",
                "model": "mimo-v2.5-tts",
                "voice": "Mia",
                "style_prompt": "自然",
            },
        )
        assert response.status_code in [200, 500]

    def test_preview_without_api_key_returns_error(self, client, monkeypatch):
        monkeypatch.delenv("MIMO_API_KEY", raising=False)
        monkeypatch.delenv("TTS_API_KEY", raising=False)
        response = client.post(
            "/api/tts/preview",
            json={"text": "测试文本", "model": "mimo-v2.5-tts", "voice": "Mia"},
        )
        assert response.status_code == 500
        assert "MIMO_API_KEY" in response.json()["detail"]

    def test_preview_with_invalid_model_returns_error(self, client, monkeypatch):
        monkeypatch.delenv("MIMO_API_KEY", raising=False)
        monkeypatch.delenv("TTS_API_KEY", raising=False)
        response = client.post(
            "/api/tts/preview", json={"text": "测试文本", "model": ""}
        )
        assert response.status_code in [400, 422, 500]

    def test_preview_request_no_authorization_header(self, client):
        """预览请求应包含 api-key 头"""
        with (
            patch("requests.post") as mock_post,
            patch("apps.control_plane.routes.tts.app_config") as mock_config,
        ):
            mock_config.get_api_key.return_value = "test-api-key"
            mock_config.get_api_base_url.return_value = "https://api.xiaomimimo.com/v1"
            mock_config.get_tts_config.return_value = {"provider": "mimo"}

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"audio": {"data": "dGVzdA=="}}}]
            }
            mock_post.return_value = mock_response

            response = client.post(
                "/api/tts/preview",
                json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
            )

            assert mock_post.called, (
                f"requests.post 应被调用，但返回 status={response.status_code}"
            )
            call_kwargs = mock_post.call_args[1]
            headers = call_kwargs.get("headers", {})

            assert "api-key" in headers, "应包含 api-key 头"

    # ── #221: preview passes qwen fields ─────────────────────────────

    def test_preview_passes_qwen_fields_to_config(self, client):
        """preview 端点应将 request 的 qwen 字段写入 config 再调用 provider"""
        with (
            patch("requests.post") as mock_post,
            patch("apps.control_plane.routes.tts.app_config") as mock_config,
        ):
            mock_config.get_api_key.return_value = "test-api-key"
            mock_config.get_api_base_url.return_value = (
                "https://dashscope.aliyuncs.com/api/v1"
            )

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "output": {"audio": {"url": "https://example.com/audio.wav"}}
            }
            mock_post.return_value = mock_response

            client.post(
                "/api/tts/preview",
                json={
                    "text": "测试文本",
                    "model": "qwen3-tts-flash",
                    "voice": "Rocky",
                    "instructions": "用粤语朗读",
                    "optimize_instructions": True,
                    "language_type": "Cantonese",
                },
            )

            # Verify QwenTTSProvider received the qwen fields in its payload
            call_args = mock_post.call_args_list[0]
            payload = call_args[1]["json"]
            assert payload["input"]["instructions"] == "用粤语朗读"
            assert payload["input"]["optimize_instructions"] is True
            assert payload["input"]["language_type"] == "Cantonese"

    # ── #222: voice/model 归属校验 ────────────────────────────────────

    def test_preview_mimo_model_invalid_voice_returns_422(self, client):
        """MiMo 模型 + Qwen 音色 'Rocky' → 422"""
        response = client.post(
            "/api/tts/preview",
            json={
                "text": "测试文本",
                "model": "mimo-v2.5-tts",
                "voice": "Rocky",
            },
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Rocky" in detail

    def test_preview_voicedesign_model_any_voice_passes(self, client):
        """voicedesign 模型发送任意 voice → 正常，不触发校验"""
        # 422 if missing voice_design_prompt is ok (MiMo API rejects it),
        # but must NOT be 422 from voice validation
        response = client.post(
            "/api/tts/preview",
            json={
                "text": "测试文本",
                "model": "mimo-v2.5-tts-voicedesign",
                "voice": "Rocky",
                "voice_design_prompt": "年轻女性",
            },
        )
        # voicedesign needs a valid prompt to succeed — 200 or 500 from MiMo API
        # but never 422 from our voice validation
        assert response.status_code != 422

    def test_preview_valid_mimo_voice_passes(self, client):
        """有效 MiMo voice/model 组合正常预览（200 或 500，不 422）"""
        response = client.post(
            "/api/tts/preview",
            json={
                "text": "测试文本",
                "model": "mimo-v2.5-tts",
                "voice": "Mia",
            },
        )
        assert response.status_code != 422


class TestTTSConfigNewFieldsRoundTrip:
    """PUT /api/tts/config → GET /api/tts/config 新字段可还原

    使用 mock 控制模块级 config_manager 以避免读取/写入真实配置文件。
    """

    @pytest.fixture
    def client(self):
        app = create_app()
        with TestClient(app) as c:
            yield c

    def _mock_manager(self):
        """Return a dict-based manager mock: get returns stored config, save stores it."""
        from packages.provider_config.tts_config import TTSConfig

        store: dict[str, TTSConfig] = {}

        def _get_config(project_id: str | None = None) -> TTSConfig:
            key = project_id or "__global__"
            return store.get(key, TTSConfig().with_defaults())

        def _save_config(config: TTSConfig, project_id: str | None = None) -> None:
            key = project_id or "__global__"
            store[key] = config

        return _get_config, _save_config

    def test_save_and_restore_qwen_fields(self, client):
        """PUT 含 instructions/language_type/optimize_instructions → GET 可还原"""
        get_mock, save_mock = self._mock_manager()
        with (
            patch(
                "apps.control_plane.routes.tts.config_manager.get_config",
                side_effect=get_mock,
            ),
            patch(
                "apps.control_plane.routes.tts.config_manager.save_config",
                side_effect=save_mock,
            ),
        ):
            config = {
                "model": "qwen3-tts-flash",
                "voice": "Rocky",
                "instructions": "用粤语朗读，语速适中",
                "optimize_instructions": True,
                "language_type": "Cantonese",
            }
            put_resp = client.put("/api/tts/config", json=config)
            assert put_resp.status_code == 200
            assert put_resp.json()["success"] is True

            get_resp = client.get("/api/tts/config")
            assert get_resp.status_code == 200
            data = get_resp.json()
            assert data["instructions"] == "用粤语朗读，语速适中"
            assert data["optimize_instructions"] is True
            assert data["language_type"] == "Cantonese"

    def test_save_and_restore_voiceclone_voicedesign_fields(self, client):
        """PUT 含 voice_clone_sample_path/voice_clone_mime_type/optimize_text_preview → GET 可还原"""
        get_mock, save_mock = self._mock_manager()
        with (
            patch(
                "apps.control_plane.routes.tts.config_manager.get_config",
                side_effect=get_mock,
            ),
            patch(
                "apps.control_plane.routes.tts.config_manager.save_config",
                side_effect=save_mock,
            ),
        ):
            config = {
                "model": "mimo-v2.5-tts-voicedesign",
                "voice_clone_sample_path": "/tmp/sample.mp3",
                "voice_clone_mime_type": "audio/mpeg",
                "optimize_text_preview": True,
            }
            put_resp = client.put("/api/tts/config", json=config)
            assert put_resp.status_code == 200
            assert put_resp.json()["success"] is True

            get_resp = client.get("/api/tts/config")
            assert get_resp.status_code == 200
            data = get_resp.json()
            assert data["voice_clone_sample_path"] == "/tmp/sample.mp3"
            assert data["voice_clone_mime_type"] == "audio/mpeg"
            assert data["optimize_text_preview"] is True

    def test_present_in_response(self, client):
        """GET 响应中所有 6 个新字段都存在（字段名验证）"""
        get_mock, save_mock = self._mock_manager()
        with patch(
            "apps.control_plane.routes.tts.config_manager.get_config",
            side_effect=get_mock,
        ):
            get_resp = client.get("/api/tts/config")
            assert get_resp.status_code == 200
            data = get_resp.json()
            for field in (
                "instructions",
                "optimize_instructions",
                "language_type",
                "voice_clone_sample_path",
                "voice_clone_mime_type",
                "optimize_text_preview",
            ):
                assert field in data, f"missing field: {field}"


class TestTTSConfigCacheInvalidation:
    """274: save_tts_config → ConfigReader.reload() 集成测试。"""

    def test_put_config_triggers_config_reader_reload(self, client):
        """PUT 修改 language_type → ConfigReader.get_tts_config() 读到新值。"""
        put_resp = client.put(
            "/api/tts/config",
            json={"language_type": "Cantonese"},
        )
        assert put_resp.status_code == 200

        reader = client.app.state.config_reader
        cfg = reader.get_tts_config()  # 读顶层 tts，不再依赖 active_product_id
        assert cfg.get("language_type") == "Cantonese"

    def test_multiple_puts_refresh_cache_each_time(self, client):
        """多次 PUT 每次都能读到最新值（不重启应用）。"""
        reader = client.app.state.config_reader

        client.put(
            "/api/tts/config", json={"language_type": "Cantonese"}
        ).raise_for_status()
        cfg1 = reader.get_tts_config()
        assert cfg1.get("language_type") == "Cantonese"

        client.put(
            "/api/tts/config", json={"language_type": "English"}
        ).raise_for_status()
        cfg2 = reader.get_tts_config()
        assert cfg2.get("language_type") == "English"


class TestTTSPreviewResponse:
    """TTS preview response format tests (WAV content-type, malformed rejection, PCM16 preservation)"""

    @pytest.fixture
    def client(self):
        app = create_app()
        with TestClient(app) as c:
            yield c

    def test_preview_response_wav_content_type(
        self, client, wav_bytes: Callable[..., bytes]
    ):
        """当 audio_format=wav 时，响应应为 audio/wav"""
        source_audio = wav_bytes()
        with (
            patch("requests.post") as mock_post,
            patch("apps.control_plane.routes.tts.app_config") as mock_config,
        ):
            mock_config.get_api_key.return_value = "test-api-key"
            mock_config.get_api_base_url.return_value = "https://api.xiaomimimo.com/v1"
            mock_config.get_tts_config.return_value = {"provider": "mimo"}

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "audio": {
                                "data": base64.b64encode(source_audio).decode("ascii")
                            }
                        }
                    }
                ]
            }
            mock_post.return_value = mock_response

            response = client.post(
                "/api/tts/preview",
                json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/wav"
            assert "preview.wav" in response.headers.get("content-disposition", "")
            assert response.content == source_audio
            with wave.open(io.BytesIO(response.content), "rb") as wav_file:
                assert wav_file.getnframes() / wav_file.getframerate() > 0

    def test_preview_rejects_non_wav_payload_without_leaking_provider_data(
        self, client
    ):
        provider_secret = "secret-provider-response"
        with (
            patch("requests.post") as mock_post,
            patch("apps.control_plane.routes.tts.app_config") as mock_config,
        ):
            mock_config.get_api_key.return_value = "secret-api-key"
            mock_response = MagicMock(status_code=200)
            mock_response.json.return_value = {
                "audio": base64.b64encode(provider_secret.encode()).decode("ascii")
            }
            mock_post.return_value = mock_response

            response = client.post(
                "/api/tts/preview",
                json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
            )

            assert response.status_code == 502
            assert response.json()["detail"] == "TTS returned invalid WAV audio"
            assert provider_secret not in response.text
            assert "secret-api-key" not in response.text

    @pytest.mark.parametrize(
        "malformation",
        ["header-only", "zero-frame", "zero-framerate", "truncated-frame-data"],
    )
    def test_preview_rejects_malformed_wav_container(
        self,
        client,
        wav_bytes: Callable[..., bytes],
        malformation: str,
    ):
        if malformation == "header-only":
            source_audio = b"RIFF\x04\x00\x00\x00WAVE"
        elif malformation == "zero-frame":
            source_audio = wav_bytes(0)
        elif malformation == "zero-framerate":
            malformed_audio = bytearray(wav_bytes(1))
            malformed_audio[24:32] = b"\x00" * 8
            source_audio = bytes(malformed_audio)
        else:
            source_audio = wav_bytes()[:-2]
        with (
            patch("requests.post") as mock_post,
            patch("apps.control_plane.routes.tts.app_config") as mock_config,
        ):
            mock_config.get_api_key.return_value = "test-api-key"
            mock_response = MagicMock(status_code=200)
            mock_response.json.return_value = {
                "audio": base64.b64encode(source_audio).decode("ascii")
            }
            mock_post.return_value = mock_response

            response = client.post(
                "/api/tts/preview",
                json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
            )

            assert response.status_code == 502
            assert response.json()["detail"] == "TTS returned invalid WAV audio"

    def test_preview_preserves_raw_pcm16_payload(self, client):
        source_audio = b"\x00\x00\x01\x00\xff\x7f"
        config = TTSConfig(
            model="mimo-v2.5-tts",
            voice="Mia",
            audio_format="pcm16",
        ).with_defaults()
        with (
            patch("requests.post") as mock_post,
            patch("apps.control_plane.routes.tts.app_config") as mock_config,
            patch("apps.control_plane.routes.tts.config_manager") as mock_manager,
        ):
            mock_config.get_api_key.return_value = "test-api-key"
            mock_manager.get_config.return_value.with_defaults.return_value = config
            mock_response = MagicMock(status_code=200)
            mock_response.json.return_value = {
                "audio": base64.b64encode(source_audio).decode("ascii")
            }
            mock_post.return_value = mock_response

            response = client.post(
                "/api/tts/preview",
                json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/L16;rate=24000;channels=1"
            assert "preview.pcm" in response.headers["content-disposition"]
            assert response.content == source_audio
