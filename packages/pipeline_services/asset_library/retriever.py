from __future__ import annotations

import logging
import random

from packages.pipeline_services.asset_library.models import AssetRecord, Category, load_keyword_map

logger = logging.getLogger(__name__)


MAX_CLIP_REUSE = 2


class AssetRetriever:
    def __init__(self, repository) -> None:
        self.repository = repository
        self.keyword_map = load_keyword_map()

    def retrieve(self, script_text: str, product: str) -> list[dict]:
        logger.info(f"[Retriever] 开始检索素材: product={product}, 文案长度={len(script_text)}字")
        sentences = self._split_sentences(script_text)
        logger.info(f"[Retriever] 文案拆分为 {len(sentences)} 个句子")
        selected: list[dict] = []

        for i, sentence in enumerate(sentences):
            category = self._parse_sentence(sentence)
            if category:
                candidates = self.repository.query_by_category(product, category)
                candidates = [c for c in candidates if c.usage_count < MAX_CLIP_REUSE]
                if candidates:
                    chosen = min(candidates, key=lambda c: c.usage_count)
                    selected.append({
                        "sentence": sentence,
                        "category": category.value,
                        "file_path": chosen.file_path,
                        "asset_id": chosen.asset_id,
                        "method": "keyword_match",
                    })
                    self.repository.increment_usage(chosen.asset_id)
                    logger.info(f"[Retriever] 句子 {i+1}: 关键词匹配 → {category.value}, 素材={chosen.asset_id}")
                    continue

            fallback = self._fallback(product)
            if fallback:
                selected.append({
                    "sentence": sentence,
                    "category": fallback.category.value,
                    "file_path": fallback.file_path,
                    "asset_id": fallback.asset_id,
                    "method": "fallback",
                })
                self.repository.increment_usage(fallback.asset_id)
                logger.info(f"[Retriever] 句子 {i+1}: 降级匹配 → {fallback.category.value}, 素材={fallback.asset_id}")
            else:
                logger.warning(f"[Retriever] 句子 {i+1}: 无可用素材! 句子内容: {sentence[:30]}...")

        logger.info(f"[Retriever] 检索完成: {len(selected)}/{len(sentences)} 句子匹配成功")
        return selected

    def _parse_sentence(self, sentence: str) -> Category | None:
        for cat in Category:
            keywords = self.keyword_map.get(cat.value, [])
            for kw in keywords:
                if kw in sentence:
                    return cat
        return None

    def _fallback(self, product: str) -> AssetRecord | None:
        all_assets = self.repository.query_all_available(product)
        available = [a for a in all_assets if a.usage_count < MAX_CLIP_REUSE]
        if available:
            return min(available, key=lambda a: a.usage_count)
        if all_assets:
            return min(all_assets, key=lambda a: a.usage_count)
        return None

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        import re
        raw = re.split(r"[。！？\n;；]", text)
        return [s.strip() for s in raw if len(s.strip()) >= 4]
