"""Tests for WorkerHttpClient — proxy bypass and URL resolution."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from apps.runtime_worker.http_client import WorkerHttpClient


def _make_client(base_url: str = "http://127.0.0.1:17890") -> WorkerHttpClient:
    return WorkerHttpClient(
        base_url=base_url,
        worker_id="worker-mac",
        worker_version="0.1.0",
        capabilities=["mac-local"],
    )


def test_http_client_absolute_url_handles_absolute_and_relative_paths() -> None:
    client = _make_client()

    assert (
        client._absolute_url("http://example.com/bundle") == "http://example.com/bundle"
    )
    assert (
        client._absolute_url("https://example.com/bundle")
        == "https://example.com/bundle"
    )
    assert client._absolute_url("/bundle") == "http://127.0.0.1:17890/bundle"
    assert client._absolute_url("bundle") == "http://127.0.0.1:17890/bundle"


def test_http_client_session_trust_env_is_false() -> None:
    """trust_env=False is the core mechanism that bypasses HTTP_PROXY for internal comms."""
    client = _make_client()
    assert client._session.trust_env is False


def test_http_client_poll_bypasses_environment_proxy() -> None:
    """With trust_env=False, poll() reaches base_url directly even when HTTP_PROXY is set."""
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"command": "idle", "next_poll_after_seconds": 5}

    client = _make_client()
    client._session = MagicMock()
    client._session.post.return_value = mock_resp

    with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:7897"}):
        result = client.poll()

    client._session.post.assert_called_once_with(
        "http://127.0.0.1:17890/workers/poll",
        json={
            "worker_id": "worker-mac",
            "worker_version": "0.1.0",
            "capabilities": ["mac-local"],
            "current_tasks": [],
            "free_slots": 1,
        },
        timeout=15,
    )
    assert result == {"command": "idle", "next_poll_after_seconds": 5}
