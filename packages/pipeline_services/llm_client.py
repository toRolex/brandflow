from __future__ import annotations

from typing import Any

import requests
from requests import HTTPError


class LLMError(Exception):
    """LLM 客户端调用异常。"""


class LLMClient:
    """通用 LLM HTTP 客户端。

    封装 OpenAI 兼容的 /chat/completions 端点，统一异常处理与响应提取。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """发送聊天请求并返回 assistant 文本内容。

        Args:
            messages: OpenAI 格式的消息列表。
            temperature: 采样温度（可选）。
            max_tokens: 最大输出 token 数（可选）。
            **kwargs: 透传给 API 的额外参数。

        Returns:
            assistant 消息的 content 字段。

        Raises:
            LLMError: HTTP 错误、空 choices 或空 content。
        """
        url = self.base_url if self.base_url.endswith("/chat/completions") else f"{self.base_url}/chat/completions"
        headers = {
            "api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        body.update(kwargs)

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise LLMError("empty choices in LLM response")
            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise LLMError("empty content in LLM response")
            return content
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            raise LLMError(f"[{status}] {exc}") from exc
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(str(exc)) from exc
