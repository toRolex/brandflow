from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from packages.pipeline_services.llm_client import LLMClient
from pathlib import Path

from packages.knowledge_store.store import KnowledgeStore
from packages.pipeline_services.script_service.prompts import (
    build_first_half_messages,
    build_second_half_messages,
    build_cantonese_conversion_messages,
    build_cover_title_messages,
    DEFAULT_BRAND,
)
from packages.pipeline_services.script_service.quality import (
    compact_len,
    validate_script,
    validate_cantonese_script,
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
        scene: str | None = None,
        material: str | None = None,
        custom_prompt: str = "",
        mock: bool = False,
        language: str = "mandarin",
        product_config: dict | None = None,
        knowledge_config: dict | None = None,
    ) -> ScriptResult:
        if mock:
            return self._mock_result(product, brand, language)

        # Pre-compute knowledge selling points if enabled
        knowledge_selling_points = self._format_knowledge_selling_points(
            knowledge_config
        )

        best_text = ""
        best_quality: dict[str, Any] = {}
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            first_half = self._generate_half(
                build_first_half_messages(
                    product, brand, scene, material, custom_prompt,
                    product_config=product_config,
                    knowledge_selling_points=knowledge_selling_points,
                )
            )
            first_len = compact_len(first_half)

            second_half = self._generate_half(
                build_second_half_messages(
                    product,
                    brand,
                    scene,
                    material,
                    first_half,
                    first_len,
                    custom_prompt,
                    product_config=product_config,
                    knowledge_selling_points=knowledge_selling_points,
                )
            )

            full_text = first_half + second_half
            quality = validate_script(full_text, product, brand)

            if not quality["ok"]:
                best_text, best_quality = self._track_shorter(
                    full_text, quality, best_text, best_quality
                )
                continue

            if language == "cantonese":
                cantonese_text = self.to_cantonese(full_text, product, brand)
                cantonese_quality = validate_cantonese_script(
                    cantonese_text, product, brand
                )
                if cantonese_quality["ok"]:
                    return ScriptResult(
                        full_text=cantonese_text,
                        first_half=cantonese_text[: len(cantonese_text) // 2],
                        second_half=cantonese_text[len(cantonese_text) // 2 :],
                        attempts=attempt,
                        quality=cantonese_quality,
                    )
                best_text, best_quality = self._track_shorter(
                    cantonese_text, cantonese_quality, best_text, best_quality
                )
            else:
                return ScriptResult(
                    full_text=full_text,
                    first_half=first_half,
                    second_half=second_half,
                    attempts=attempt,
                    quality=quality,
                )

            best_text, best_quality = self._track_shorter(
                full_text, quality, best_text, best_quality
            )

        return ScriptResult(
            full_text=best_text,
            first_half=best_text[: len(best_text) // 2],
            second_half=best_text[len(best_text) // 2 :],
            attempts=MAX_GENERATION_ATTEMPTS,
            quality=best_quality,
        )

    def to_cantonese(self, mandarin_text: str, product: str, brand: str) -> str:
        """将普通话脚本转换为口语化粤语。"""
        messages = build_cantonese_conversion_messages(mandarin_text, product, brand)
        raw = self._call_llm(messages)
        return raw.strip()

    def generate_cover_title(
        self, script_text: str, product: str, brand: str
    ) -> dict[str, Any]:
        """根据脚本生成封面标题和高亮关键词。标题限制 10-15 字。"""
        messages = build_cover_title_messages(script_text, product, brand)
        raw = self._call_llm(messages)
        try:
            payload = self._extract_json(raw)
            title = str(payload.get("title", "")).strip()
            if len(title) > 15:
                title = title[:15]
            highlight_words = payload.get("highlight_words", [])
            if isinstance(highlight_words, str):
                highlight_words = [
                    w.strip() for w in highlight_words.split(",") if w.strip()
                ]
            return {"text": title, "highlight_words": highlight_words}
        except (ValueError, json.JSONDecodeError):
            return {"text": product, "highlight_words": [product]}

    @staticmethod
    def _format_knowledge_selling_points(
        knowledge_config: dict | None,
    ) -> str:
        """Format top-K selling points from KnowledgeStore into a prompt string.

        Returns empty string if knowledge_config is None, disabled, or no items found.
        """
        if not knowledge_config:
            return ""
        if not knowledge_config.get("enabled", True):
            return ""

        store_dir = knowledge_config.get("store_dir", "")
        if not store_dir:
            return ""

        top_k = knowledge_config.get("top_k", 5)

        store = KnowledgeStore(Path(store_dir))
        items = store.get_top_k_items(item_type="selling_point", k=top_k)

        if not items:
            return ""

        lines = []
        for item in items:
            lines.append(f"- {item.title}：{item.content}")
        return "\n".join(lines)

    @staticmethod
    def _track_shorter(
        text: str, quality: dict[str, Any], best_text: str, best_quality: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        if len(text) < len(best_text) or not best_text:
            return text, quality
        return best_text, best_quality

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
    def _mock_result(
        product: str, brand: str, language: str = "mandarin"
    ) -> ScriptResult:
        if language == "cantonese":
            first = f"雲南深山裡邊藏住一種寶貝，就係鮮嫩嘅{product}，採摘之後即刻送到你手中，今日教大家點樣煮先好食"
            second = f"鑊度落油燒熱落食材，徹底煮熟先至可以安心享用，{brand}嘅品質值得信賴，快啲落單試下啦"
        else:
            first = f"来自优质产地的{product}，精挑细选后送到你手中，今天教大家怎么做好吃"
            second = f"锅里放油烧热下食材，确保完全煮熟才能安心享用，{brand}的品质值得信赖，赶紧下单尝尝吧"
        full = first + "。" + second + "。"
        if language == "cantonese":
            quality = validate_cantonese_script(full, product, brand)
        else:
            quality = validate_script(full, product, brand)
        return ScriptResult(
            full_text=full,
            first_half=first + "。",
            second_half=second + "。",
            attempts=0,
            quality=quality,
            mock=True,
        )
