from __future__ import annotations

import logging
import random
from collections.abc import Callable

from packages.pipeline_services.asset_library.models import AssetRecord

logger = logging.getLogger(__name__)


MAX_CLIP_REUSE = 2


class AssetRetriever:
    def __init__(
        self, repository, classify_fn: Callable[[str], str | None] | None = None
    ) -> None:
        self.repository = repository
        self._classify_fn = classify_fn

    def retrieve(self, script_text: str, product: str) -> list[dict]:
        logger.info(
            f"[Retriever] 开始检索素材: product={product}, 文案长度={len(script_text)}字"
        )
        sentences = self._split_sentences(script_text)
        logger.info(f"[Retriever] 文案拆分为 {len(sentences)} 个句子")
        selected: list[dict] = []

        for i, sentence in enumerate(sentences):
            requested_category_name = self._classify(sentence)
            if requested_category_name:
                candidates = self.repository.query_by_category_name(
                    product, requested_category_name
                )
                candidates = [c for c in candidates if c.usage_count < MAX_CLIP_REUSE]
                if candidates:
                    chosen = random.choice(candidates)
                    selected.append(
                        {
                            "sentence": sentence,
                            "category": requested_category_name,
                            "requested_category": requested_category_name,
                            "file_path": chosen.file_path,
                            "asset_id": chosen.asset_id,
                            "duration_seconds": chosen.duration_seconds,
                            "method": "llm_match",
                            "visual_type": "clip",
                        }
                    )
                    self.repository.increment_usage(chosen.asset_id)
                    logger.info(
                        f"[Retriever] 句子 {i + 1}: LLM分类 → {requested_category_name}, 素材={chosen.asset_id}"
                    )
                    continue

            fallback = self._fallback(product)
            if fallback:
                requested_cat = requested_category_name or "未知"
                selected.append(
                    {
                        "sentence": sentence,
                        "category": fallback.category_name(),
                        "requested_category": requested_cat,
                        "file_path": fallback.file_path,
                        "asset_id": fallback.asset_id,
                        "duration_seconds": fallback.duration_seconds,
                        "method": "fallback",
                        "visual_type": "clip",
                    }
                )
                self.repository.increment_usage(fallback.asset_id)
                logger.info(
                    f"[Retriever] 句子 {i + 1}: 降级匹配 想匹配{requested_cat} → {fallback.category_name()}, 素材={fallback.asset_id}"
                )
            else:
                logger.warning(
                    f"[Retriever] 句子 {i + 1}: 无可用素材! 句子内容: {sentence[:30]}..."
                )
                selected.append(
                    {
                        "sentence": sentence,
                        "category": requested_category_name or "",
                        "requested_category": requested_category_name or "",
                        "file_path": "",
                        "asset_id": "",
                        "duration_seconds": 0.0,
                        "method": "",
                        "visual_type": "unresolved",
                    }
                )
                logger.info(f"[Retriever] 句子 {i + 1}: 标记为 unresolved")

        logger.info(
            f"[Retriever] 检索完成: {len(selected)}/{len(sentences)} 句子匹配成功"
        )
        return selected

    def _classify(self, sentence: str) -> str | None:
        if self._classify_fn is None:
            return None
        return self._classify_fn(sentence)

    def _fallback(self, product: str) -> AssetRecord | None:
        all_assets = self.repository.query_all_available(product)
        available = [a for a in all_assets if a.usage_count < MAX_CLIP_REUSE]
        if available:
            return random.choice(available)
        if all_assets:
            return random.choice(all_assets)
        return None

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        import re

        raw = re.split(r"[。！？\n;；]", text)
        return [s.strip() for s in raw if len(s.strip()) >= 4]


def _compute_trim_params(clips: list[dict], audio_duration: float) -> list[dict]:
    """为每个素材计算裁剪参数：起始偏移(ss)和裁剪时长(duration)。

    每句分配均等时长，ss 在 [0, 1] 随机偏移。
    如果素材时长不足，会调整 ss 确保能裁剪出足够时长。
    """
    if not clips:
        return []

    per_clip = audio_duration / len(clips)
    params: list[dict] = []
    spare_capacity: list[float] = []

    for clip in clips:
        source_duration = float(clip.get("duration_seconds", 0) or 0)
        ss = random.uniform(0, 1)
        duration = per_clip
        spare = 0.0

        if source_duration > 0:
            if ss + duration > source_duration:
                ss = max(0, source_duration - duration)
            if ss < 0:
                ss = 0
            max_duration = max(0.1, source_duration - ss)
            duration = min(duration, max_duration)
            spare = max(0.0, max_duration - duration)

        params.append(
            {
                **clip,
                "ss": ss,
                "duration": duration,
            }
        )
        spare_capacity.append(spare)

    remaining = max(0.0, audio_duration - sum(item["duration"] for item in params))
    if remaining > 0:
        for index, item in enumerate(params):
            if remaining <= 0:
                break
            spare = spare_capacity[index]
            if spare <= 0:
                continue
            extra = min(spare, remaining)
            item["duration"] += extra
            remaining -= extra

    for item in params:
        item["ss"] = round(item["ss"], 3)
        item["duration"] = round(item["duration"], 3)
    return params
