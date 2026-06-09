"""测试 voiceclone 请求构建"""
import pytest
import base64
from pathlib import Path
from packages.pipeline_services.tts_provider import MiMoTTSProvider
from packages.provider_config.tts_config import TTSConfig


@pytest.fixture
def temp_audio_file(tmp_path):
    audio_file = tmp_path / "voice_clone_sample.mp3"
    audio_file.write_bytes(b"fake audio data for testing")
    return audio_file


def test_build_voiceclone_request(temp_audio_file):
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts-voiceclone",
        voice_clone_sample_path=str(temp_audio_file),
        voice_clone_mime_type="audio/mpeg",
        audio_format="wav",
    )
    request = provider._build_voiceclone_request("测试文本", config)
    assert request["model"] == "mimo-v2.5-tts-voiceclone"
    voice = request["audio"]["voice"]
    assert voice.startswith("data:audio/mpeg;base64,")
    b64_part = voice.split(",", 1)[1]
    decoded = base64.b64decode(b64_part)
    assert decoded == b"fake audio data for testing"
    assistant_msg = next(m for m in request["messages"] if m["role"] == "assistant")
    assert assistant_msg["content"] == "测试文本"


def test_build_voiceclone_request_with_style(temp_audio_file):
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts-voiceclone",
        voice_clone_sample_path=str(temp_audio_file),
        voice_clone_mime_type="audio/mpeg",
        audio_format="wav",
        style_control_mode="simple",
        style_prompt="温柔亲切",
    )
    request = provider._build_voiceclone_request("测试文本", config)
    user_msg = next(m for m in request["messages"] if m["role"] == "user")
    assert user_msg["content"] == "温柔亲切"


def test_build_voiceclone_request_wav_mime(temp_audio_file):
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts-voiceclone",
        voice_clone_sample_path=str(temp_audio_file),
        voice_clone_mime_type="audio/wav",
        audio_format="wav",
    )
    request = provider._build_voiceclone_request("测试文本", config)
    voice = request["audio"]["voice"]
    assert voice.startswith("data:audio/wav;base64,")


def test_build_request_routes_to_voiceclone(temp_audio_file):
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts-voiceclone",
        voice_clone_sample_path=str(temp_audio_file),
        voice_clone_mime_type="audio/mpeg",
        audio_format="wav",
    )
    request = provider._build_request("测试文本", config)
    assert request["model"] == "mimo-v2.5-tts-voiceclone"
    assert "data:audio/mpeg;base64," in request["audio"]["voice"]
