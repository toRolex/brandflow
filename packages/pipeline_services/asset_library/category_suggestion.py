"""AI-powered category suggestion for the shared asset library.

Scans a random sample of video assets, uses Vision API to describe
each frame, then clusters descriptions via LLM into a recommended
category system.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from packages.file_store.paths import shared_asset_db_path
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.provider_config.app_config import AppConfigManager

logger = logging.getLogger(__name__)

_DESCRIBE_FRAME_PROMPT = (
    "You are an AI assistant that describes video frame content in Chinese. "
    "Look at this image from a video clip and describe what you see. "
    "Focus on: what objects are present, what action is happening, "
    "and the visual composition (close-up, wide shot, etc.). "
    "Keep your description to 1-2 sentences in Chinese."
)

_CATEGORIZE_PROMPT_TEMPLATE = """你是一个视频素材分类系统设计师。以下是 {count} 个视频片段的帧描述集合：

{descriptions}

请根据以上帧描述，将这些视频片段归纳为 5-15 个类别。每个类别应该：

1. **互斥** — 类别之间不重叠
2. **描述性强** — 类别名和描述能清晰说明该类视频的拍摄内容和角度
3. **行业无关** — 不要假设特定行业，保持通用
4. **每个类别包含一个 vision_prompt（英文）** — 用于 AI 自动帧分类的提示

返回一个 JSON 数组，每个元素格式为：
{{
    "id": "英文短标识（如 product_display）",
    "name": "中文类别名",
    "description": "该类别的简短中文描述",
    "vision_prompt": "English prompt for AI to classify frames into this category"
}}

只返回 JSON 数组，不要有其他文字。
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_vision_api_config() -> dict:
    """Resolve vision API connection details from AppConfigManager."""
    manager = AppConfigManager()
    config = manager.get_vision_config()
    return {
        "provider": config.get("provider", "xiaomi"),
        "api_key": manager.get_vision_api_key(),
        "endpoint": manager.get_vision_endpoint(),
        "model": manager.get_vision_model(),
    }


def _resolve_llm_api_config() -> dict:
    """Resolve LLM API connection details from AppConfigManager."""
    manager = AppConfigManager()
    config = manager.get_llm_config()
    return {
        "provider": config.get("provider", "deepseek"),
        "api_key": manager.get_llm_api_key(),
        "endpoint": manager.get_llm_endpoint(),
        "model": manager.get_category_suggestion_model(),
    }


def _ffmpeg_path() -> str:
    return os.environ.get("FFMPEG_PATH", "ffmpeg")


def _get_media_duration(video_path: Path) -> float | None:
    """Get video duration in seconds using ffprobe."""
    ffprobe = os.environ.get("FFPROBE_PATH", "ffprobe")
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def _extract_frame(video_path: Path, output_dir: Path) -> Path | None:
    """Extract a single frame from the midpoint of a video.

    Returns the path to the extracted frame, or ``None`` on failure.
    """
    try:
        duration = _get_media_duration(video_path)
        if duration is None or duration <= 0:
            logger.warning("Cannot determine duration for %s", video_path)
            return None

        midpoint = duration / 2
        output_path = output_dir / f"{video_path.stem}.jpg"
        ffmpeg = _ffmpeg_path()

        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-ss",
                str(midpoint),
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-q:v",
                "2",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return output_path if output_path.exists() else None
    except Exception as exc:
        logger.warning("Frame extraction failed for %s: %s", video_path, exc)
        return None


def _describe_frame_with_vision(
    image_path: Path,
    api_key: str,
    endpoint: str,
    model: str,
) -> str | None:
    """Send a frame image to the Vision API and return a text description.

    Uses the same OpenAI-compatible format as ``VisionClient``.
    """
    import base64

    import requests

    image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    ext = image_path.suffix.lower().replace(".", "")
    media_type = (
        f"image/{ext}" if ext in ("jpg", "jpeg", "png", "webp") else "image/jpeg"
    )
    data_url = f"data:{media_type};base64,{image_b64}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _DESCRIBE_FRAME_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 500,
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        return str(content).strip()
    except Exception as exc:
        logger.warning("Vision API call failed for %s: %s", image_path.name, exc)
        return None


def _cluster_descriptions(
    descriptions: list[str],
    api_key: str,
    endpoint: str,
    model: str,
) -> list[dict]:
    """Send frame descriptions to the LLM for clustering into categories.

    Returns a list of category dicts with keys: ``id``, ``name``,
    ``description``, ``vision_prompt``.
    """
    import requests

    desc_text = "\n".join(f"- {d}" for d in descriptions if d)
    prompt = _CATEGORIZE_PROMPT_TEMPLATE.format(
        count=len(descriptions), descriptions=desc_text
    )

    url = (
        endpoint
        if endpoint.endswith("/chat/completions")
        else f"{endpoint}/chat/completions"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个专业的视频素材分类系统设计师。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 3000,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]

        # Try to extract JSON array from the response
        cleaned = content.strip()
        # Find the first [ and last ]
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1:
            cleaned = cleaned[start : end + 1]

        result = json.loads(cleaned)
        if isinstance(result, list):
            validated: list[dict] = []
            for item in result:
                if isinstance(item, dict) and "id" in item and "name" in item:
                    validated.append(
                        {
                            "id": str(item.get("id", "")),
                            "name": str(item.get("name", "")),
                            "description": str(item.get("description", "")),
                            "vision_prompt": str(item.get("vision_prompt", "")),
                        }
                    )
            return validated
        return []
    except Exception as exc:
        logger.warning("LLM clustering failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def suggest_categories(
    root_dir: Path,
    sample_size: int = 20,
    llm_config: dict | None = None,
    vision_config: dict | None = None,
) -> dict:
    """Scan the shared asset library and suggest an AI-generated category system.

    Parameters
    ----------
    root_dir:
        Project root directory.
    sample_size:
        Maximum number of assets to sample for analysis.
    llm_config:
        Optional override for LLM config (provider, api_key, endpoint, model).
        When ``None``, resolves from ``AppConfigManager``.
    vision_config:
        Optional override for Vision config (provider, api_key, endpoint, model).
        When ``None``, resolves from ``AppConfigManager``.

    Returns
    -------
    dict
        A dict with keys:
        - ``categories``: list of suggested category dicts
        - ``sampled_assets``: number of actually sampled assets
        - ``model_used``: LLM model used for clustering
        - ``descriptions``: list of per-frame descriptions (for transparency)
        - ``errors``: list of error messages (empty on success)
    """
    logger.info(
        "Category suggestion: root_dir=%s, sample_size=%d", root_dir, sample_size
    )

    errors: list[str] = []

    # 1. Connect to the shared asset DB
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        msg = "Asset library database not found"
        logger.warning(msg)
        return {
            "categories": [],
            "sampled_assets": 0,
            "model_used": "",
            "descriptions": [],
            "errors": [msg],
        }

    repo = AssetRepository(db_path)
    product = os.environ.get("PRODUCT", "")

    # 2. Query available assets
    if product:
        assets = repo.query_all_available(product)
    else:
        # Query across all products — use raw SQL
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM assets WHERE status != 'disabled' ORDER BY usage_count ASC"
        ).fetchall()
        conn.close()
        from packages.pipeline_services.asset_library.models import AssetRecord

        from packages.pipeline_services.asset_library.repository import (
            row_to_record,
        )

        assets = []
        for row in rows:
            try:
                assets.append(row_to_record(row))
            except Exception:
                continue

    if not assets:
        msg = "No available assets found in the library"
        logger.warning(msg)
        return {
            "categories": [],
            "sampled_assets": 0,
            "model_used": "",
            "descriptions": [],
            "errors": [msg],
        }

    # 3. Randomly sample N assets (or fewer if library is small)
    import random

    actual_sample = min(sample_size, len(assets))
    sampled = random.sample(assets, actual_sample)

    logger.info("Sampled %d assets out of %d total", actual_sample, len(assets))

    # 4. Extract frames to a temp directory
    with tempfile.TemporaryDirectory(prefix="cat_suggest_") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        frame_paths: list[tuple[Path, Path | None]] = []

        for asset in sampled:
            video_path = Path(asset.file_path)
            if not video_path.exists():
                frame_paths.append((video_path, None))
                continue
            frame = _extract_frame(video_path, tmpdir)
            frame_paths.append((video_path, frame))

        # 5. Resolve API configs
        if vision_config is None:
            vision_config = _resolve_vision_api_config()
        if llm_config is None:
            llm_config = _resolve_llm_api_config()

        vision_api_key = vision_config.get("api_key", "")
        vision_endpoint = vision_config.get("endpoint", "")
        vision_model = vision_config.get("model", "")

        llm_api_key = llm_config.get("api_key", "")
        llm_endpoint = llm_config.get("endpoint", "")
        llm_model = llm_config.get("model", "")

        # 6. Describe each frame via Vision API
        descriptions: list[str] = []
        for video_path, frame_path in frame_paths:
            if frame_path is None:
                descriptions.append("")
                continue
            desc = _describe_frame_with_vision(
                frame_path,
                api_key=vision_api_key,
                endpoint=vision_endpoint,
                model=vision_model,
            )
            descriptions.append(desc or "")

        # Filter out empty descriptions
        valid_descriptions = [d for d in descriptions if d]

        if not valid_descriptions:
            errors.append("No frame descriptions could be generated")
            return {
                "categories": [],
                "sampled_assets": actual_sample,
                "model_used": llm_model,
                "descriptions": descriptions,
                "errors": errors,
            }

        # 7. Cluster descriptions into categories via LLM
        categories = _cluster_descriptions(
            valid_descriptions,
            api_key=llm_api_key,
            endpoint=llm_endpoint,
            model=llm_model,
        )

    if not categories:
        errors.append("LLM did not return valid categories")

    return {
        "categories": categories,
        "sampled_assets": actual_sample,
        "model_used": llm_model,
        "descriptions": descriptions,
        "errors": errors,
    }


