from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.pipeline_services.llm_client import LLMClient, LLMError


class TestLLMClient:
    def _make_client(self, **overrides):
        defaults = {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-pro",
            "timeout": 60,
        }
        defaults.update(overrides)
        return LLMClient(**defaults)

    @patch("packages.pipeline_services.llm_client.requests")
    def test_chat_sends_correct_payload(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "hello"}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_resp

        client = self._make_client()
        result = client.chat([{"role": "user", "content": "hi"}])

        assert result == "hello"
        call_kwargs = mock_requests.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["model"] == "deepseek-v4-pro"
        assert body["messages"] == [{"role": "user", "content": "hi"}]
        assert body["stream"] is False

    @patch("packages.pipeline_services.llm_client.requests")
    def test_chat_raises_on_http_error(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.raise_for_status.side_effect = Exception("Rate limited")
        mock_requests.post.return_value = mock_resp

        client = self._make_client()
        with pytest.raises(LLMError, match="429|Rate limited"):
            client.chat([{"role": "user", "content": "hi"}])

    @patch("packages.pipeline_services.llm_client.requests")
    def test_chat_raises_on_empty_choices(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": []}
        mock_resp.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_resp

        client = self._make_client()
        with pytest.raises(LLMError, match="empty|no choices"):
            client.chat([{"role": "user", "content": "hi"}])

    @patch("packages.pipeline_services.llm_client.requests")
    def test_chat_passes_extra_params(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_resp

        client = self._make_client()
        client.chat(
            [{"role": "user", "content": "hi"}],
            temperature=0.5,
            max_tokens=100,
        )

        body = (
            mock_requests.post.call_args.kwargs.get("json")
            or mock_requests.post.call_args[1].get("json")
        )
        assert body["temperature"] == 0.5
        assert body["max_tokens"] == 100

    @patch("packages.pipeline_services.llm_client.requests")
    def test_chat_constructs_correct_url(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_resp

        client = self._make_client(base_url="https://api.deepseek.com/v1")
        client.chat([{"role": "user", "content": "hi"}])

        url = (
            mock_requests.post.call_args.args[0]
            if mock_requests.post.call_args.args
            else mock_requests.post.call_args.kwargs.get("url")
        )
        assert url == "https://api.deepseek.com/v1/chat/completions"
