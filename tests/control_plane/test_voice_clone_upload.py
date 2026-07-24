"""测试 voiceclone 样本上传接口"""

import pytest
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(root_dir=tmp_path)
    with TestClient(app) as c:
        yield c


def test_upload_voice_clone_sample_mp3(client, tmp_path):
    sample_content = b"fake mp3 audio data"
    files = {"file": ("sample.mp3", sample_content, "audio/mpeg")}
    response = client.post(
        "/api/tts/voice-clone-sample",
        files=files,
        params={"project_id": "test_project"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "voice_clone_sample.mp3" in data["path"]
    saved_path = (
        tmp_path / "config" / "projects" / "test_project" / "voice_clone_sample.mp3"
    )
    assert saved_path.exists()
    assert saved_path.read_bytes() == sample_content


def test_upload_voice_clone_sample_wav(client, tmp_path):
    sample_content = b"fake wav audio data"
    files = {"file": ("sample.wav", sample_content, "audio/wav")}
    response = client.post("/api/tts/voice-clone-sample", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["mime_type"] == "audio/wav"


def test_upload_voice_clone_sample_invalid_format(client):
    files = {"file": ("sample.txt", b"not audio", "text/plain")}
    response = client.post("/api/tts/voice-clone-sample", files=files)
    assert response.status_code == 400
    assert "只支持 mp3 或 wav 格式" in response.json()["detail"]


def test_upload_voice_clone_sample_too_large(client):
    large_content = b"x" * (11 * 1024 * 1024)
    files = {"file": ("large.mp3", large_content, "audio/mpeg")}
    response = client.post("/api/tts/voice-clone-sample", files=files)
    assert response.status_code == 400
    assert "超过 10MB" in response.json()["detail"]


def test_upload_voice_clone_sample_updates_config(client, tmp_path):
    sample_content = b"fake mp3 audio data"
    files = {"file": ("sample.mp3", sample_content, "audio/mpeg")}
    response = client.post(
        "/api/tts/voice-clone-sample",
        files=files,
        params={"project_id": "test_project"},
    )
    assert response.status_code == 200
    from packages.provider_config.tts_config import TTSConfigManager

    config_manager = TTSConfigManager(config_dir=str(tmp_path / "config"))
    config = config_manager.get_config(product_id="test_project")
    assert config.voice_clone_sample_path is not None
    assert config.voice_clone_mime_type == "audio/mpeg"
