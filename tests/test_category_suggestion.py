"""Tests for the AI category suggestion endpoint contract."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def test_suggest_empty_library() -> None:
    """POST /api/assets/categories/suggest returns ``{"suggestions": []}``
    when there are no assets in the library, instead of raising an error.
    """
    mock_empty_result = {
        "categories": [],
        "sampled_assets": 0,
        "model_used": "",
        "descriptions": [],
        "errors": ["No available assets found in the library"],
    }

    target = (
        "apps.control_plane.routes.category_suggestion"
        ".suggest_categories"
    )

    with patch(target, return_value=mock_empty_result):
        app = create_app(root_dir=Path.cwd())
        client = TestClient(app)
        resp = client.post("/api/assets/categories/suggest", json={})

    assert resp.status_code == 200
    data = resp.json()

    # ---- outer key: ``suggestions`` (not ``categories``) ----
    assert "suggestions" in data, (
        "Empty response must contain 'suggestions' key, got %s" % list(data.keys())
    )
    assert "categories" not in data, (
        "Empty response must NOT contain 'categories' key"
    )

    suggestions = data["suggestions"]
    assert isinstance(suggestions, list)
    assert len(suggestions) == 0, (
        "Empty library should produce empty suggestions list"
    )

def test_suggest_response_contract() -> None:
    """POST /api/assets/categories/suggest returns ``{"suggestions": [...]}``
    with each item containing ``label``/``description``/``vision_prompt``.

    This test validates the backend response matches the frontend
    ``SuggestCategory`` type and the ``api.suggestCategories()`` caller.
    """
    mock_suggest_result = {
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

    target = (
        "apps.control_plane.routes.category_suggestion"
        ".suggest_categories"
    )

    with patch(target, return_value=mock_suggest_result):
        app = create_app(root_dir=Path.cwd())
        client = TestClient(app)
        resp = client.post("/api/assets/categories/suggest", json={})

    assert resp.status_code == 200
    data = resp.json()

    # ---- outer key: ``suggestions`` (not ``categories``) ----
    assert "suggestions" in data, (
        "Response must contain 'suggestions' key, got %s" % list(data.keys())
    )
    assert "categories" not in data, (
        "Response must NOT contain 'categories' key"
    )

    suggestions = data["suggestions"]
    assert isinstance(suggestions, list)
    assert len(suggestions) == 2

    # ---- each item: ``label`` / ``description`` / ``vision_prompt`` ----
    for item in suggestions:
        assert "label" in item, "Each suggestion must have 'label'"
        assert "description" in item, "Each suggestion must have 'description'"
        assert "vision_prompt" in item, (
            "Each suggestion must have 'vision_prompt'"
        )
        # Fields from the internal model that must NOT leak
        assert "name" not in item, (
            "Suggestion must NOT contain 'name' (use 'label')"
        )
        assert "id" not in item, "Suggestion must NOT contain 'id'"

    # ---- verify specific values are mapped correctly ----
    assert suggestions[0]["label"] == "产品展示"
    assert suggestions[0]["description"] == "展示产品外观和包装的镜头"
    assert suggestions[0]["vision_prompt"] == "product or packaging in frame"

    assert suggestions[1]["label"] == "使用场景"
    assert suggestions[1]["description"] == "用户实际使用产品的画面"
    assert suggestions[1]["vision_prompt"] == "person using the product"
