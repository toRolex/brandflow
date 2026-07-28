from __future__ import annotations

import random
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass

from packages.pipeline_services.asset_library.models import AssetRecord
from packages.pipeline_services.asset_library.retriever import (
    MAX_CLIP_REUSE,
    _has_usable_duration,
)


@dataclass
class ReplacementDiagnostics:
    """Counters explaining why no replacement was found."""

    total: int = 0
    same_id: int = 0
    overused: int = 0
    bad_duration: int = 0
    job_overused: int = 0


@dataclass
class ReplacementDecision:
    """Outcome of attempting to pick a replacement asset for a clip position.

    ``chosen`` is ``None`` when no usable alternative exists. In that case
    ``reason`` and ``diagnostics`` describe why the search failed.
    """

    chosen: AssetRecord | None
    reason: str = ""
    diagnostics: ReplacementDiagnostics | None = None


def select_replacement(
    asset_repo,
    product: str,
    category: str,
    exclude_asset_id: str,
    current_asset_ids: Collection[str] | None = None,
) -> ReplacementDecision:
    """Select a replacement asset for a clip position.

    The function is side-effect free: it does not update ``selected_clips.json``
    or ``usage_count``. Callers are responsible for persisting any changes.

    Selection rules:

    - Query the asset index for ``product`` + ``category``.
    - Exclude the currently assigned ``asset_id``.
    - Exclude assets with unusable duration (shorter than
      ``MIN_CLIP_DURATION_SECONDS`` when a duration is present).
    - Prefer assets that are not already heavily used inside the current job
      (``current_asset_ids``). The hard reuse limit is applied per-job, not
      globally, so a material that was used in earlier jobs can still be used
      as long as it is fresh in this video.
    - If every candidate is already used in the current job, fall back to the
      least-used material globally so the user still gets a replacement rather
      than an error.
    - Ties are broken uniformly at random.
    """
    if not product:
        return ReplacementDecision(
            chosen=None,
            reason="job product is empty; cannot query asset library",
        )
    if not category:
        return ReplacementDecision(
            chosen=None,
            reason="clip category is empty; cannot query asset library",
        )

    all_candidates = asset_repo.query_by_category_name(product, category)
    job_counts = Counter(current_asset_ids or ())

    # Base pool: same category, not the rejected asset, duration OK.
    base_candidates = [
        c
        for c in all_candidates
        if c.asset_id != exclude_asset_id and _has_usable_duration(c)
    ]

    # Prefer candidates that are still fresh inside this job.
    candidates = [
        c
        for c in base_candidates
        if job_counts[c.asset_id] < MAX_CLIP_REUSE
    ]

    if candidates:
        # Prefer fewer in-job uses, then lower global usage_count.
        candidates.sort(key=lambda c: (job_counts[c.asset_id], c.usage_count))
        min_key = (job_counts[candidates[0].asset_id], candidates[0].usage_count)
        best = [c for c in candidates if (job_counts[c.asset_id], c.usage_count) == min_key]
        return ReplacementDecision(chosen=random.choice(best))

    # Fallback: every candidate is already used in this job. Pick the least-used
    # globally so the user always gets a different asset when one exists.
    if base_candidates:
        base_candidates.sort(key=lambda c: c.usage_count)
        min_usage = base_candidates[0].usage_count
        best = [c for c in base_candidates if c.usage_count == min_usage]
        return ReplacementDecision(chosen=random.choice(best))

    diagnostics = ReplacementDiagnostics(
        total=len(all_candidates),
        same_id=sum(1 for c in all_candidates if c.asset_id == exclude_asset_id),
        overused=sum(
            1 for c in all_candidates if c.usage_count >= MAX_CLIP_REUSE
        ),
        bad_duration=sum(
            1 for c in all_candidates if not _has_usable_duration(c)
        ),
        job_overused=sum(
            1
            for c in all_candidates
            if c.asset_id != exclude_asset_id
            and _has_usable_duration(c)
            and job_counts[c.asset_id] >= MAX_CLIP_REUSE
        ),
    )

    reason = _build_no_replacement_reason(product, category, diagnostics)
    return ReplacementDecision(
        chosen=None,
        reason=reason,
        diagnostics=diagnostics,
    )


def _build_no_replacement_reason(
    product: str,
    category: str,
    diagnostics: ReplacementDiagnostics,
) -> str:
    """Build a human-readable reason why no replacement was found."""
    total = diagnostics.total
    same_id = diagnostics.same_id
    overused = diagnostics.overused
    bad_duration = diagnostics.bad_duration
    job_overused = diagnostics.job_overused

    if total == 0:
        return f"no assets found for product={product}, category={category}"
    if total == same_id:
        return (
            f"only the current asset exists in product={product}, "
            f"category={category}"
        )

    parts: list[str] = []
    if job_overused:
        parts.append(f"{job_overused} already used in this job (>= {MAX_CLIP_REUSE})")
    if overused:
        parts.append(f"{overused} overused globally (>= {MAX_CLIP_REUSE})")
    if bad_duration:
        parts.append(f"{bad_duration} with unusable duration")
    if same_id:
        parts.append(f"{same_id} is the current asset")

    return (
        f"no usable alternative in product={product}, category={category}"
        f" ({'; '.join(parts)})"
    )
