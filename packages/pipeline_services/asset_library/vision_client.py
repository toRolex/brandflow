from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

from packages.pipeline_services.asset_library.category_config import default_categories

logger = logging.getLogger(__name__)

_VISION_PROMPT = """你是一个视频素材分类助手。请识别这张图片属于以下哪个类别，只返回一个类别名称：

可选类别：{categories}

返回格式：{{"category": "类别名", "confidence": 0.0-1.0}}"""


def build_vision_prompt(category_names: list[str] | None = None) -> str:
    """Build a vision classification prompt from a list of category names.

    Parameters
    ----------
    category_names:
        Category names to include in the prompt. Falls back to the legacy
        default categories when ``None`` or empty.
    """
    if category_names:
        cats = ", ".join(category_names)
    else:
        cats = ", ".join(c.name for c in default_categories())
    return _VISION_PROMPT.format(categories=cats)


class VisionClient:
    def __init__(
        self,
        api_key: str = "",
        endpoint: str = "",
        model: str = "",
        provider: str = "",
        categories: list[str] | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("VISION_API_KEY", "")
        self.endpoint = endpoint or os.getenv("VISION_API_URL", "")
        self.model = model or os.getenv("VISION_MODEL", "")
        self.provider = provider or os.getenv("VISION_PROVIDER", "openai")
        self._vision_prompt = build_vision_prompt(categories)

    def classify_frame(self, image_path: Path) -> dict:
        logger.info(
            f"[Vision] 开始分类: {image_path.name}, provider={self.provider}, model={self.model}"
        )
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        ext = image_path.suffix.lower().replace(".", "")
        media_type = (
            f"image/{ext}" if ext in ("jpg", "jpeg", "png", "webp") else "image/jpeg"
        )

        import requests

        try:
            if self.provider == "claude":
                payload, headers = self._build_claude_request(image_b64, media_type)
                logger.debug(f"[Vision] 请求 Claude API: {self.endpoint}")
                resp = requests.post(
                    self.endpoint, json=payload, headers=headers, timeout=60
                )
                resp.raise_for_status()
                result = self._parse_claude_response(resp.json())
            else:
                # Default: OpenAI-compatible format
                data_url = f"data:{media_type};base64,{image_b64}"
                payload, headers = self._build_openai_request(data_url)
                logger.debug(f"[Vision] 请求 OpenAI API: {self.endpoint}")
                resp = requests.post(
                    self.endpoint, json=payload, headers=headers, timeout=60
                )
                resp.raise_for_status()
                result = self._parse_openai_response(resp.json())

            logger.info(
                f"[Vision] 分类成功: {image_path.name} → {result.get('category')} (置信度: {result.get('confidence', 0):.2f})"
            )
            return result
        except requests.exceptions.Timeout:
            logger.error(
                f"[Vision] 请求超时: {image_path.name}, endpoint={self.endpoint}"
            )
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(
                f"[Vision] HTTP 错误: {image_path.name}, status={e.response.status_code}, body={e.response.text[:200]}"
            )
            raise
        except Exception as e:
            logger.error(
                f"[Vision] 分类失败: {image_path.name}, error={type(e).__name__}: {e}"
            )
            raise

    def _build_openai_request(self, data_url: str) -> tuple[dict, dict]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._vision_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "max_tokens": 1000,
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return payload, headers

    def _parse_openai_response(self, data: dict) -> dict:
        raw = data["choices"][0]["message"]["content"]
        if isinstance(raw, list):
            raw_text = "".join(
                part.get("text", "") for part in raw if isinstance(part, dict)
            )
        else:
            raw_text = str(raw)
        try:
            result = json.loads(raw_text)
            return {
                "category": result.get("category", ""),
                "confidence": float(result.get("confidence", 0.5)),
            }
        except (json.JSONDecodeError, KeyError):
            return {"category": raw_text.strip(), "confidence": 0.5}

    def _build_claude_request(
        self, image_b64: str, media_type: str
    ) -> tuple[dict, dict]:
        payload = {
            "model": self.model,
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._vision_prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        return payload, headers

    def _parse_claude_response(self, data: dict) -> dict:
        raw_text = str(data["content"][0]["text"])
        try:
            result = json.loads(raw_text)
            return {
                "category": result.get("category", ""),
                "confidence": float(result.get("confidence", 0.5)),
            }
        except (json.JSONDecodeError, KeyError, IndexError):
            return {"category": raw_text.strip(), "confidence": 0.5}


def resolve_vision_config(
    providers_payload: dict,
    secrets: "SecretStore | None" = None,
    reader: "ConfigReader | None" = None,
) -> dict:
    """Resolve vision provider config from ConfigReader + SecretStore or injected deps.

    When *secrets* and *reader* are provided they are used directly;
    otherwise falls back to constructing ``ConfigReader`` + ``SecretStore``.
    """
    if secrets is not None and reader is not None:
        config = reader.get_vision_config()
        return {
            "provider": config.get("provider", "xiaomi"),
            "api_key": secrets.get_vision_api_key(reader),
            "endpoint": secrets.get_vision_endpoint(reader),
            "model": secrets.get_vision_model(reader),
        }

    from packages.provider_config.config_reader import ConfigReader
    from packages.provider_config.secret_store import SecretStore

    _reader = ConfigReader()
    _secrets = SecretStore()
    config = _reader.get_vision_config()
    return {
        "provider": config.get("provider", "xiaomi"),
        "api_key": _secrets.get_vision_api_key(_reader),
        "endpoint": _secrets.get_vision_endpoint(_reader),
        "model": _secrets.get_vision_model(_reader),
    }
