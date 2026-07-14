"""Tests for the AI category suggestion endpoint contract."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def suggest_client() -> tuple[TestClient, Mock]:
    """Create a TestClient with ``suggest_categories`` patched.

    The mock is active for the duration of the test.  Assign
    ``mock.return_value`` in each test to control what the route
    returns, then call ``client.post(...)``.
    """
    target = "apps.control_plane.routes.category_suggestion.suggest_categories"
    with patch(target) as mock:
        app = create_app(root_dir=Path.cwd())
        client = TestClient(app)
        yield client, mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_suggest_empty_library(suggest_client: tuple[TestClient, Mock]) -> None:
    """POST /api/assets/categories/suggest returns ``{"suggestions": []}``
    when there are no assets in the library, instead of raising an error.
    """
    client, mock = suggest_client
    mock.return_value = {
        "categories": [],
        "sampled_assets": 0,
        "model_used": "",
        "descriptions": [],
        "errors": ["No available assets found in the library"],
    }

    resp = client.post("/api/assets/categories/suggest", json={})

    assert resp.status_code == 200
    data = resp.json()

    # ---- outer key: ``suggestions`` (not ``categories``) ----
    assert "suggestions" in data, (
        "Empty response must contain 'suggestions' key, got %s" % list(data.keys())
    )
    assert "categories" not in data, "Empty response must NOT contain 'categories' key"

    suggestions = data["suggestions"]
    assert isinstance(suggestions, list)
    assert len(suggestions) == 0, "Empty library should produce empty suggestions list"


def test_suggest_response_contract(
    suggest_client: tuple[TestClient, Mock],
) -> None:
    """POST /api/assets/categories/suggest returns ``{"suggestions": [...]}``
    with each item containing ``label``/``description``/``vision_prompt``.

    This test validates the backend response matches the frontend
    ``SuggestCategory`` type and the ``api.suggestCategories()`` caller.
    """
    client, mock = suggest_client
    mock.return_value = {
        "categories": [
            {
                "id": "product_display",
                "name": "产品展示",
                "description": "展示产品外观和包装的镜头",
                "vision_prompt": "product or packaging in frame",
            },
            {
                "id": "usage_scene",
                "name": "使用场景",
                "description": "用户实际使用产品的画面",
                "vision_prompt": "person using the product",
            },
        ],
        "sampled_assets": 10,
        "model_used": "test-model",
        "descriptions": ["frame desc 1", "frame desc 2"],
        "errors": [],
    }

    resp = client.post("/api/assets/categories/suggest", json={})

    assert resp.status_code == 200
    data = resp.json()

    # ---- outer key: ``suggestions`` (not ``categories``) ----
    assert "suggestions" in data, (
        "Response must contain 'suggestions' key, got %s" % list(data.keys())
    )
    assert "categories" not in data, "Response must NOT contain 'categories' key"

    suggestions = data["suggestions"]
    assert isinstance(suggestions, list)
    assert len(suggestions) == 2

    # ---- each item: ``label`` / ``description`` / ``vision_prompt`` ----
    for item in suggestions:
        assert "label" in item, "Each suggestion must have 'label'"
        assert "description" in item, "Each suggestion must have 'description'"
        assert "vision_prompt" in item, "Each suggestion must have 'vision_prompt'"
        # Fields from the internal model that must NOT leak
        assert "name" not in item, "Suggestion must NOT contain 'name' (use 'label')"
        assert "id" not in item, "Suggestion must NOT contain 'id'"

    # ---- verify specific values are mapped correctly ----
    assert suggestions[0]["label"] == "产品展示"
    assert suggestions[0]["description"] == "展示产品外观和包装的镜头"
    assert suggestions[0]["vision_prompt"] == "product or packaging in frame"

    assert suggestions[1]["label"] == "使用场景"
    assert suggestions[1]["description"] == "用户实际使用产品的画面"
    assert suggestions[1]["vision_prompt"] == "person using the product"


def test_suggest_empty_body_returns_200(
    suggest_client: tuple[TestClient, Mock],
) -> None:
    """POST with empty JSON body must be accepted and use defaults."""
    client, mock = suggest_client
    mock.return_value = {
        "categories": [],
        "sampled_assets": 0,
        "model_used": "default-model",
        "descriptions": [],
        "errors": ["No available assets found in the library"],
    }

    resp = client.post("/api/assets/categories/suggest", json={})

    assert resp.status_code == 200
    mock.assert_called_once()
    data = resp.json()
    assert "suggestions" in data
    assert "errors" in data
    assert data["errors"] == ["No available assets found in the library"]


def test_suggest_truly_empty_body(
    suggest_client: tuple[TestClient, Mock],
) -> None:
    """POST with truly empty body (``content=b""``) must return 200
    with ``suggestions`` and ``errors`` keys.
    """
    client, mock = suggest_client
    mock.return_value = {
        "categories": [],
        "sampled_assets": 0,
        "model_used": "default-model",
        "descriptions": [],
        "errors": ["No available assets found in the library"],
    }

    resp = client.post(
        "/api/assets/categories/suggest",
        content=b"",
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    mock.assert_called_once()
    data = resp.json()
    assert "suggestions" in data
    assert "errors" in data


def test_suggest_errors_are_returned(
    suggest_client: tuple[TestClient, Mock],
) -> None:
    """Backend errors are surfaced in the response ``errors`` array."""
    client, mock = suggest_client
    mock.return_value = {
        "categories": [
            {"id": "a", "name": "A", "description": "desc", "vision_prompt": "prompt"},
        ],
        "sampled_assets": 3,
        "model_used": "model",
        "descriptions": ["d1"],
        "errors": ["Vision API 超时", "部分素材无法读取"],
    }

    resp = client.post("/api/assets/categories/suggest", json={})

    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"]
    assert data["errors"] == ["Vision API 超时", "部分素材无法读取"]
