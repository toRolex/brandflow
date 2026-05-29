from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from packages.provider_config.runtime_env import VISION_ENV_MAPPINGS, _section_overrides


_VISION_PROMPT = """你是一个菌菇视频素材分类助手。请识别这张图片属于以下哪个类别，只返回一个类别名称：

可选类别：产地溯源, 筛选分拣, 清洗泡发, 切配处理, 下锅入锅, 烹饪翻炒, 出锅装盘, 成品展示, 试吃品尝, 产品特写

返回格式：{"category": "类别名", "confidence": 0.0-1.0}"""


class VisionClient:
    def __init__(self, api_key: str = "", endpoint: str = "", model: str = "") -> None:
        self.api_key = api_key or os.getenv("VISION_API_KEY", "")
        self.endpoint = endpoint or os.getenv("VISION_API_URL", "")
        self.model = model or os.getenv("VISION_MODEL", "")

    def classify_frame(self, image_path: Path) -> dict:
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        ext = image_path.suffix.lower().replace(".", "")
        media_type = f"image/{ext}" if ext in ("jpg", "jpeg", "png", "webp") else "image/jpeg"

        data_url = f"data:{media_type};base64,{image_b64}"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "max_tokens": 300,
            "temperature": 0,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        import requests
        resp = requests.post(self.endpoint, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        raw_text = data["choices"][0]["message"]["content"]

        try:
            result = json.loads(raw_text)
            return {"category": result.get("category", ""), "confidence": float(result.get("confidence", 0.5))}
        except (json.JSONDecodeError, KeyError):
            return {"category": raw_text.strip(), "confidence": 0.5}


def resolve_vision_config(providers_payload: dict) -> dict:
    """Resolve vision provider config from the full providers.yaml payload."""
    vision_section = providers_payload.get("providers", {}).get("vision", {})
    selected = vision_section.get("selected", "")
    providers = vision_section.get("providers", {})
    overrides = _section_overrides(selected, providers, VISION_ENV_MAPPINGS, "VISION_PROVIDER")
    return {
        "api_key": overrides.get("VISION_API_KEY", ""),
        "endpoint": overrides.get("VISION_API_URL", ""),
        "model": overrides.get("VISION_MODEL", ""),
    }
