from __future__ import annotations

import random
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
) -> ReplacementDecision:
    """Select a replacement asset for a clip position.

    The function is side-effect free: it does not update ``selected_clips.json``
    or ``usage_count``. Callers are responsible for persisting any changes.

    Selection rules (mirroring the legacy ``reject-clip`` / ``re-search``
    behavior but unified):

    - Query the asset index for ``product`` + ``category``.
    - Exclude the currently assigned ``asset_id``.
    - Exclude assets whose ``usage_count >= MAX_CLIP_REUSE``.
    - Exclude assets with unusable duration (shorter than
      ``MIN_CLIP_DURATION_SECONDS`` when a duration is present).
    - Pick uniformly at random from the remaining candidates.

    Known limitation: ``set-blank``, ``set-asset`` and ``restore`` currently do
    not adjust ``usage_count``. This helper only covers the re-search path.
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
    candidates = [
        c
        for c in all_candidates
        if c.asset_id != exclude_asset_id
        and c.usage_count < MAX_CLIP_REUSE
        and _has_usable_duration(c)
    ]

    if candidates:
        return ReplacementDecision(chosen=random.choice(candidates))

    diagnostics = ReplacementDiagnostics(
        total=len(all_candidates),
        same_id=sum(1 for c in all_candidates if c.asset_id == exclude_asset_id),
        overused=sum(
            1 for c in all_candidates if c.usage_count >= MAX_CLIP_REUSE
        ),
        bad_duration=sum(
            1 for c in all_candidates if not _has_usable_duration(c)
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

    if total == 0:
        return f"no assets found for product={product}, category={category}"
    if total == same_id:
        return (
            f"only the current asset exists in product={product}, "
            f"category={category}"
        )

    parts: list[str] = []
    if overused:
        parts.append(f"{overused} overused (>= {MAX_CLIP_REUSE})")
    if bad_duration:
        parts.append(f"{bad_duration} with unusable duration")
    if same_id:
        parts.append(f"{same_id} is the current asset")

    return (
        f"no usable alternative in product={product}, category={category}"
        f" ({'; '.join(parts)})"
    )
