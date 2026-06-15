from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from packages.pipeline_services.llm_client import LLMClient
from packages.pipeline_services.script_service.prompts import (
    build_first_half_messages,
    build_second_half_messages,
    DEFAULT_BRAND,
    DEFAULT_SCENE,
    DEFAULT_MATERIAL,
)
from packages.pipeline_services.script_service.quality import (
    compact_len,
    validate_script,
)

MAX_GENERATION_ATTEMPTS = 3


@dataclass
class ScriptResult:
    full_text: str
    first_half: str
    second_half: str
    attempts: int
    quality: dict[str, Any]
    mock: bool = False


class ScriptGenerator:
    def __init__(self, config: Any):
        self._client = LLMClient(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            timeout=180,
        )

    def run(
        self,
        product: str,
        brand: str = DEFAULT_BRAND,
        scene: str = DEFAULT_SCENE,
        material: str = DEFAULT_MATERIAL,
        custom_prompt: str = "",
        mock: bool = False,
    ) -> ScriptResult:
        if mock:
            return self._mock_result(product, brand)

        best_text = ""
        best_quality: dict[str, Any] = {}
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            first_half = self._generate_half(
                build_first_half_messages(product, brand, scene, material, custom_prompt)
            )
            first_len = compact_len(first_half)

            second_half = self._generate_half(
                build_second_half_messages(
                    product, brand, scene, material,
                    first_half, first_len, custom_prompt,
                )
            )

            full_text = first_half + second_half
            quality = validate_script(full_text, product, brand)

            if quality["ok"]:
                return ScriptResult(
                    full_text=full_text,
                    first_half=first_half,
                    second_half=second_half,
                    attempts=attempt,
                    quality=quality,
                )

            if len(full_text) < len(best_text) or not best_text:
                best_text = full_text
                best_quality = quality

        return ScriptResult(
            full_text=best_text,
            first_half=best_text[: len(best_text) // 2],
            second_half=best_text[len(best_text) // 2 :],
            attempts=MAX_GENERATION_ATTEMPTS,
            quality=best_quality,
        )

    def _generate_half(self, messages: list[dict[str, str]]) -> str:
        raw = self._call_llm(messages)
        payload = self._extract_json(raw)
        sentences = self._extract_sentences(payload)
        return "。".join(sentences) + "。" if sentences else ""

    def _call_llm(self, messages: list[dict[str, str]]) -> str:
        return self._client.chat(messages)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM 未返回可解析的 JSON")
        return json.loads(text[start : end + 1])

    @staticmethod
    def _extract_sentences(payload: dict[str, Any]) -> list[str]:
        sentences = []
        for key in sorted(payload.keys()):
            value = str(payload[key]).strip()
            value = re.sub(r"\s+", "", value)
            value = value.strip("，,。！？!? \t\r\n")
            if value:
                sentences.append(value)
        return sentences

    @staticmethod
    def _mock_result(product: str, brand: str) -> ScriptResult:
        first = f"云南深山里藏着一种宝贝，它就是鲜嫩的{product}，采摘后立刻送到你手中，今天教大家怎么做好吃"
        second = f"锅里放油烧热下菌子，充分烹熟才能安心享用，{brand}的品质值得信赖，赶紧下单尝尝吧"
        full = first + "。" + second + "。"
        quality = validate_script(full, product, brand)
        return ScriptResult(
            full_text=full,
            first_half=first + "。",
            second_half=second + "。",
            attempts=0,
            quality=quality,
            mock=True,
        )
