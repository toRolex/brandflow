"""Embedding-based retrieval helpers.

Task 7:
  - cosine_similarity(a, b)
  - fetch_embedding(text) via ConfigReader / SecretStore
"""

from __future__ import annotations

import math

import requests

from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length float vectors.

    Raises ValueError when vectors differ in length or either has zero
    magnitude.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector dimension mismatch: {len(a)} vs {len(b)}")
    if not a or not b:
        raise ValueError("Empty vectors are not allowed")

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))

    if mag_a == 0.0 or mag_b == 0.0:
        raise ValueError("Cannot compute cosine similarity with a zero vector")
    return dot / (mag_a * mag_b)


def fetch_embedding(
    text: str,
    reader: ConfigReader | None = None,
    secrets: SecretStore | None = None,
) -> list[float]:
    """Fetch an embedding vector for *text* from the configured embedding API.

    Endpoint and model are non-secret values from ``app_config.json``.  The API
    key remains in ``.env`` and is resolved through ``SecretStore``.

    Returns the raw float list from the first embedding in the response.
    """
    config_reader = reader or ConfigReader()
    secret_store = secrets or SecretStore()
    config = config_reader.get_embedding_config()
    api_url = str(config.get("endpoint") or "").strip()
    if not api_url:
        api_url = secret_store.get_api_base_url("embedding")
    api_key = secret_store.get_api_key("embedding")
    model = str(config.get("model") or "").strip()

    if not api_url:
        raise RuntimeError("embedding.endpoint is not configured")
    if not api_key:
        raise RuntimeError("EMBEDDING_API_KEY is not set")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": text}

    resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    return data["data"][0]["embedding"]
