"""Embedding-based retrieval helpers.

Task 7:
  - cosine_similarity(a, b)
  - fetch_embedding(text) via EMBEDDING_API_URL / EMBEDDING_API_KEY / EMBEDDING_MODEL
"""

from __future__ import annotations

import math
import os

import requests


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length float vectors.

    Raises ValueError when vectors differ in length or either has zero
    magnitude.
    """
    if len(a) != len(b):
        raise ValueError(
            f"Vector dimension mismatch: {len(a)} vs {len(b)}"
        )
    if not a or not b:
        raise ValueError("Empty vectors are not allowed")

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))

    if mag_a == 0.0 or mag_b == 0.0:
        raise ValueError("Cannot compute cosine similarity with a zero vector")
    return dot / (mag_a * mag_b)


def fetch_embedding(text: str) -> list[float]:
    """Fetch an embedding vector for *text* from the configured embedding API.

    Reads configuration from environment variables:
      - EMBEDDING_API_URL  (required)
      - EMBEDDING_API_KEY  (required, sent as Bearer token)
      - EMBEDDING_MODEL    (defaults to ``"text-embedding-ada-002"``)

    Returns the raw float list from the first embedding in the response.
    """
    api_url = os.getenv("EMBEDDING_API_URL", "").strip()
    api_key = os.getenv("EMBEDDING_API_KEY", "").strip()
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002").strip()

    if not api_url:
        raise RuntimeError("EMBEDDING_API_URL is not set")
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
