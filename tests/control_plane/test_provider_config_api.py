from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.provider_config.catalog import default_provider_document


def test_provider_config_save_rejects_tts_provider_model_mismatch(tmp_path) -> None:
    payload = default_provider_document()
    payload["providers"]["tts"]["selected"] = "mimo"
    payload["providers"]["tts"]["providers"]["mimo"]["model"] = "qwen3-tts-flash"

    with TestClient(create_app(root_dir=tmp_path)) as client:
        response = client.put("/api/config", json=payload)

    assert response.status_code == 400
    assert "provider/model mismatch" in response.json()["detail"]


def test_provider_config_save_is_immediately_visible_to_config_reader(tmp_path) -> None:
    payload = default_provider_document()
    payload["providers"]["tts"]["selected"] = "mimo"
    payload["providers"]["tts"]["providers"]["mimo"]["model"] = "mimo-v2.5-tts"

    app = create_app(root_dir=tmp_path)
    with TestClient(app) as client:
        response = client.put("/api/config", json=payload)

    assert response.status_code == 200
    assert app.state.config_reader.get_tts_config()["provider"] == "mimo"
    assert app.state.config_reader.get_tts_config()["model"] == "mimo-v2.5-tts"
    assert not (tmp_path / "config" / "providers.yaml").exists()
