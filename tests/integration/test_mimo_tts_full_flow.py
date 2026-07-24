"""MiMo TTS 完整流程集成测试

测试 3 种模型的端到端流程：
- mimo-v2.5-tts 预置音色
- mimo-v2.5-tts-voiceclone 音色克隆
- mimo-v2-tts 预置音色
"""

import base64

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.provider_config.tts_config import TTSConfig, TTSConfigManager
from packages.pipeline_services.tts_provider import MiMoTTSProvider


@pytest.fixture
def client(tmp_path):
    app = create_app(root_dir=tmp_path)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def provider():
    return MiMoTTSProvider(api_key="test_key")


# ---------------------------------------------------------------------------
# v2.5 预置音色
# ---------------------------------------------------------------------------


class TestV25Preset:
    """mimo-v2.5-tts 预置音色完整流程"""

    def test_api_save_and_read_config(self, client):
        """1. 通过 API 保存配置，再读回验证"""
        resp = client.put(
            "/api/tts/config",
            json={
                "model": "mimo-v2.5-tts",
                "voice": "Mia",
                "audio_format": "wav",
                "randomize_voice": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        resp = client.get("/api/tts/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "mimo-v2.5-tts"
        assert data["voice"] == "Mia"
        assert data["audio_format"] == "wav"

    def test_build_request_payload(self, provider):
        """2. Provider 构建的请求结构与 API 规格一致"""
        config = TTSConfig(
            model="mimo-v2.5-tts",
            voice="Mia",
            audio_format="wav",
            randomize_voice=False,
            style_prompt="自然 清晰",
        )
        req = provider._build_request("测试文本", config)

        assert req["model"] == "mimo-v2.5-tts"
        assert req["audio"]["voice"] == "Mia"
        assert req["audio"]["format"] == "wav"
        assert req["stream"] is False
        # messages: [user=style, assistant=text]
        assert len(req["messages"]) == 2
        assert req["messages"][0]["role"] == "user"
        assert req["messages"][0]["content"] == "自然 清晰"
        assert req["messages"][1]["role"] == "assistant"
        assert req["messages"][1]["content"] == "测试文本"

    def test_randomize_voice(self, provider):
        """3. randomize_voice 开启时从 random_voices 中选取"""
        config = TTSConfig(
            model="mimo-v2.5-tts",
            voice="Mia",
            audio_format="wav",
            randomize_voice=True,
            random_voices=["苏打", "白桦"],
            style_prompt="自然",
        )
        # 多次构建，voice 应始终来自 random_voices
        voices_seen = set()
        for _ in range(50):
            req = provider._build_request("文本", config)
            voices_seen.add(req["audio"]["voice"])
        assert voices_seen <= {"苏打", "白桦"}
        assert len(voices_seen) >= 1  # 至少出现过一种


# ---------------------------------------------------------------------------
# v2.5 voiceclone 音色克隆
# ---------------------------------------------------------------------------


class TestV25VoiceClone:
    """mimo-v2.5-tts-voiceclone 音色克隆完整流程"""

    def test_upload_then_build_request(self, client, tmp_path, provider):
        """完整流程：上传样本 → 读配置 → 构建 voiceclone 请求"""
        # 1. 上传音频样本
        sample_content = b"fake mp3 audio data for voiceclone"
        files = {"file": ("sample.mp3", sample_content, "audio/mpeg")}
        resp = client.post(
            "/api/tts/voice-clone-sample",
            files=files,
            params={"project_id": "vc_project"},
        )
        assert resp.status_code == 200
        upload_data = resp.json()
        assert upload_data["success"] is True
        assert upload_data["mime_type"] == "audio/mpeg"

        # 2. 验证配置已更新（使用与 upload 路由相同的 config_dir）
        config_manager = TTSConfigManager(config_dir=str(tmp_path / "config"))
        config = config_manager.get_config(product_id="vc_project")
        assert config.voice_clone_sample_path is not None
        assert config.voice_clone_mime_type == "audio/mpeg"

        # 3. 覆盖模型为 voiceclone
        config.model = "mimo-v2.5-tts-voiceclone"
        config.audio_format = "wav"

        # 4. Provider 构建 voiceclone 请求
        req = provider._build_request("克隆测试文本", config)

        assert req["model"] == "mimo-v2.5-tts-voiceclone"
        assert req["audio"]["format"] == "wav"
        # voice 应该是 data URI
        voice_value = req["audio"]["voice"]
        assert voice_value.startswith("data:audio/mpeg;base64,")
        # 解码验证内容一致
        b64_part = voice_value.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        assert decoded == sample_content

    def test_voiceclone_sample_not_found(self, provider):
        """样本文件不存在时应抛出 TTSError"""
        from packages.pipeline_services.tts_provider import TTSError

        config = TTSConfig(
            model="mimo-v2.5-tts-voiceclone",
            audio_format="wav",
            voice_clone_sample_path="/nonexistent/path/sample.mp3",
            voice_clone_mime_type="audio/mpeg",
        )
        with pytest.raises(TTSError, match="Voice clone sample not found"):
            provider._build_request("文本", config)

    def test_voiceclone_wav_mime_type(self, client, tmp_path, provider):
        """wav 样本使用 audio/wav MIME"""
        sample_content = b"fake wav audio data"
        files = {"file": ("sample.wav", sample_content, "audio/wav")}
        resp = client.post(
            "/api/tts/voice-clone-sample",
            files=files,
            params={"project_id": "vc_wav_project"},
        )
        assert resp.status_code == 200
        assert resp.json()["mime_type"] == "audio/wav"

        config_manager = TTSConfigManager(config_dir=str(tmp_path / "config"))
        config = config_manager.get_config(product_id="vc_wav_project")
        config.model = "mimo-v2.5-tts-voiceclone"
        config.audio_format = "wav"

        req = provider._build_request("文本", config)
        assert req["audio"]["voice"].startswith("data:audio/wav;base64,")


# ---------------------------------------------------------------------------
# v2 预置音色
# ---------------------------------------------------------------------------


class TestV2Preset:
    """mimo-v2-tts 预置音色完整流程（已迁移至 qwen）"""

    def test_api_save_and_read_config(self, client):
        """1. mimo-v2-tts 保存后自动迁移为 qwen3-tts-flash"""
        resp = client.put(
            "/api/tts/config",
            json={
                "model": "mimo-v2-tts",
                "voice": "default_zh",
                "audio_format": "wav",
                "randomize_voice": False,
            },
        )
        assert resp.status_code == 200

        resp = client.get("/api/tts/config")
        data = resp.json()
        assert data["model"] == "qwen3-tts-flash"
        assert data["voice"] == "Rocky"

    def test_build_request_payload(self, provider):
        """2. Provider 构建 v2.5 请求"""
        config = TTSConfig(
            model="mimo-v2.5-tts",
            voice="default_zh",
            audio_format="wav",
            randomize_voice=False,
            style_prompt="清晰自然",
        )
        req = provider._build_request("v2.5 测试文本", config)

        assert req["model"] == "mimo-v2.5-tts"
        assert req["audio"]["voice"] == "default_zh"
        assert req["audio"]["format"] == "wav"
        assert req["stream"] is False
        assert req["messages"][1]["content"] == "v2.5 测试文本"


# ---------------------------------------------------------------------------
# 跨模型通用验证
# ---------------------------------------------------------------------------


class TestCrossModel:
    """跨模型通用行为验证"""

    def test_style_prompt_in_user_message(self, provider):
        """所有预置模型都将 style_prompt 放在 user message"""
        for model in ["mimo-v2.5-tts"]:
            config = TTSConfig(
                model=model,
                voice="test",
                audio_format="wav",
                randomize_voice=False,
                style_prompt="温暖亲切",
            )
            req = provider._build_request("文本", config)
            assert req["messages"][0]["content"] == "温暖亲切"

    def test_audio_tags_prepended(self, provider):
        """audio_tags 开启时标签拼在 assistant content 前面"""
        config = TTSConfig(
            model="mimo-v2.5-tts",
            voice="Mia",
            audio_format="wav",
            randomize_voice=False,
            audio_tags_enabled=True,
            audio_tags="(温柔)[笑声]",
        )
        req = provider._build_request("正文内容", config)
        assert req["messages"][1]["content"] == "(温柔)[笑声]正文内容"

    def test_director_mode_style(self, provider):
        """导演模式正确拼接角色/场景/指导"""
        config = TTSConfig(
            model="mimo-v2.5-tts",
            voice="Mia",
            audio_format="wav",
            randomize_voice=False,
            style_control_mode="director",
            director_character="年轻女主播",
            director_scene="新闻直播间",
            director_guidance="语速适中",
        )
        req = provider._build_request("文本", config)
        user_content = req["messages"][0]["content"]
        assert "【角色】年轻女主播" in user_content
        assert "【场景】新闻直播间" in user_content
        assert "【指导】语速适中" in user_content
