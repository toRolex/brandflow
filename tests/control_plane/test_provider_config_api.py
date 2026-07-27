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


def test_config_api_exposes_catalog_driven_runtime_settings(tmp_path) -> None:
    with TestClient(create_app(root_dir=tmp_path)) as client:
        options = client.get("/api/config/options").json()
        config = client.get("/api/config").json()

    assert options["settings"]["embedding"]["label"] == "Embedding"
    assert options["settings"]["media"]["fields"][0]["name"] == "ffmpeg_path"
    assert config["settings"]["embedding"]["model"] == "text-embedding-ada-002"
    assert config["settings"]["scene"]["transition_duration_ms"] == 500


def test_runtime_settings_save_is_immediately_visible_to_config_reader(
    tmp_path,
) -> None:
    payload = default_provider_document()
    payload["settings"]["embedding"]["model"] = "text-embedding-3-small"
    payload["settings"]["asset_library"]["category_suggestion_sample_size"] = 50
    payload["settings"]["scene"]["transition_duration_ms"] = 750

    app = create_app(root_dir=tmp_path)
    with TestClient(app) as client:
        response = client.put("/api/config", json=payload)

    assert response.status_code == 200
    assert (
        app.state.config_reader.get_embedding_config()["model"]
        == "text-embedding-3-small"
    )
    assert app.state.config_reader.get_category_suggestion_sample_size() == 50
    assert app.state.config_reader.get_scene_config()["transition_duration_ms"] == 750


def test_runtime_settings_reject_invalid_catalog_constraints(tmp_path) -> None:
    payload = default_provider_document()
    payload["settings"]["scene"]["transition_duration_ms"] = -1

    with TestClient(create_app(root_dir=tmp_path)) as client:
        response = client.put("/api/config", json=payload)

    assert response.status_code == 400
    assert "scene.transition_duration_ms" in response.json()["detail"]


def test_runtime_settings_reject_fractional_integer_field(tmp_path) -> None:
    payload = default_provider_document()
    payload["settings"]["asset_library"]["category_suggestion_sample_size"] = 20.9

    with TestClient(create_app(root_dir=tmp_path)) as client:
        response = client.put("/api/config", json=payload)

    assert response.status_code == 400
    assert "asset_library.category_suggestion_sample_size" in response.json()["detail"]


def test_runtime_settings_reject_invalid_json(tmp_path) -> None:
    payload = default_provider_document()
    payload["settings"]["scene"]["folders"] = "not-json"

    with TestClient(create_app(root_dir=tmp_path)) as client:
        response = client.put("/api/config", json=payload)

    assert response.status_code == 400
    assert "scene.folders" in response.json()["detail"]


def test_runtime_settings_reject_invalid_scene_folder_shape(tmp_path) -> None:
    payload = default_provider_document()
    payload["settings"]["scene"]["folders"] = '["not-an-object"]'

    with TestClient(create_app(root_dir=tmp_path)) as client:
        response = client.put("/api/config", json=payload)

    assert response.status_code == 400
    assert "scene.folders[0]" in response.json()["detail"]


def test_embedding_secret_is_saved_only_to_env(tmp_path) -> None:
    payload = default_provider_document()
    payload["settings"]["embedding"]["api_key"] = "embedding-secret"

    with TestClient(create_app(root_dir=tmp_path)) as client:
        response = client.put("/api/config", json=payload)

    assert response.status_code == 200
    assert response.json()["settings"]["embedding"]["api_key"] == "***"
    assert "EMBEDDING_API_KEY=embedding-secret" in (tmp_path / ".env").read_text(
        encoding="utf-8"
    )
    assert "embedding-secret" not in (
        tmp_path / "config" / "app_config.json"
    ).read_text(encoding="utf-8")
