import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


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

    def test_preview_passes_qwen_fields_to_config(self, client):
        """preview 端点应将 request 的 qwen 字段写入 config 再调用 provider"""
        with (
            patch("requests.post") as mock_post,
            patch("apps.control_plane.routes.tts.app_config") as mock_config,
        ):
            mock_config.get_api_key.return_value = "test-api-key"
            mock_config.get_api_base_url.return_value = "https://dashscope.aliyuncs.com/api/v1"

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "output": {
                    "audio": {
                        "url": "https://example.com/audio.wav"
                    }
                }
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


class TestTTSConfigNewFieldsRoundTrip:
    """PUT /api/tts/config → GET /api/tts/config 新字段可还原

    使用 mock 控制模块级 config_manager 以避免读取/写入真实配置文件。
    """

    @pytest.fixture
    def client(self):
        app = create_app()
        return TestClient(app)

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
        with patch(
            "apps.control_plane.routes.tts.config_manager.get_config",
            side_effect=get_mock,
        ), patch(
            "apps.control_plane.routes.tts.config_manager.save_config",
            side_effect=save_mock,
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
        with patch(
            "apps.control_plane.routes.tts.config_manager.get_config",
            side_effect=get_mock,
        ), patch(
            "apps.control_plane.routes.tts.config_manager.save_config",
            side_effect=save_mock,
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
