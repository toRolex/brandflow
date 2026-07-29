from __future__ import annotations

from packages.pipeline_services.asset_library.models import AssetRecord
from packages.pipeline_services.asset_library.replacement import (
    ReplacementDiagnostics,
    select_replacement,
)


class FakeAssetRepository:
    """In-memory stand-in for AssetRepository."""

    def __init__(self, assets: list[AssetRecord]) -> None:
        self._assets = assets

    def query_by_category_name(self, product: str, category: str) -> list[AssetRecord]:
        return [
            a for a in self._assets if a.product == product and a.category == category
        ]


def _asset(
    asset_id: str,
    *,
    category: str = "intro",
    product: str = "test",
    duration_seconds: float = 6.0,
    usage_count: int = 0,
    status: str = "available",
) -> AssetRecord:
    return AssetRecord(
        asset_id=asset_id,
        file_path=f"/data/{asset_id}.mp4",
        category=category,
        product=product,
        duration_seconds=duration_seconds,
        usage_count=usage_count,
        status=status,
    )


def test_empty_product_returns_reason() -> None:
    repo = FakeAssetRepository([_asset("a1")])
    decision = select_replacement(repo, "", "intro", "a1")
    assert decision.chosen is None
    assert "product is empty" in decision.reason
    assert decision.diagnostics is None


def test_empty_category_returns_reason() -> None:
    repo = FakeAssetRepository([_asset("a1")])
    decision = select_replacement(repo, "test", "", "a1")
    assert decision.chosen is None
    assert "category is empty" in decision.reason
    assert decision.diagnostics is None


def test_returns_random_candidate_excluding_current() -> None:
    repo = FakeAssetRepository([_asset("a1"), _asset("alt1"), _asset("alt2")])
    decision = select_replacement(repo, "test", "intro", "a1")
    assert decision.chosen is not None
    assert decision.chosen.asset_id in {"alt1", "alt2"}
    assert decision.diagnostics is None


def test_excludes_overused_assets() -> None:
    repo = FakeAssetRepository(
        [
            _asset("a1"),
            _asset("alt1", usage_count=2),
            _asset("alt2", usage_count=1),
        ]
    )
    decision = select_replacement(repo, "test", "intro", "a1")
    assert decision.chosen is not None
    # Lower global usage is preferred when the job has not used either asset.
    assert decision.chosen.asset_id == "alt2"


def test_excludes_short_duration_assets() -> None:
    repo = FakeAssetRepository(
        [
            _asset("a1"),
            _asset("alt1", duration_seconds=1.0),
            _asset("alt2", duration_seconds=6.0),
        ]
    )
    decision = select_replacement(repo, "test", "intro", "a1")
    assert decision.chosen is not None
    assert decision.chosen.asset_id == "alt2"


def test_prefers_assets_fresh_in_current_job() -> None:
    repo = FakeAssetRepository(
        [
            _asset("a1"),
            _asset("alt1", usage_count=5),
            _asset("alt2", usage_count=0),
        ]
    )
    decision = select_replacement(
        repo, "test", "intro", "a1", current_asset_ids=["alt2"]
    )
    assert decision.chosen is not None
    # alt2 is already used once in this job; alt1 is not used in this job,
    # so the replacement prefers alt1 to maximize variety within the video.
    assert decision.chosen.asset_id == "alt1"


def test_falls_back_to_least_used_when_all_job_overused() -> None:
    repo = FakeAssetRepository(
        [
            _asset("a1"),
            _asset("alt1", usage_count=5),
            _asset("alt2", usage_count=10),
        ]
    )
    decision = select_replacement(
        repo,
        "test",
        "intro",
        "a1",
        current_asset_ids=["alt1", "alt1", "alt2", "alt2"],
    )
    assert decision.chosen is not None
    # Both alternatives are already used >= MAX_CLIP_REUSE inside this job,
    # so we fall back to the least-used globally.
    assert decision.chosen.asset_id == "alt1"


def test_no_usable_alternative_returns_diagnostics() -> None:
    repo = FakeAssetRepository(
        [
            _asset("a1"),
            _asset("alt1", duration_seconds=1.0),
        ]
    )
    decision = select_replacement(repo, "test", "intro", "a1")
    assert decision.chosen is None
    assert "no usable alternative" in decision.reason
    assert isinstance(decision.diagnostics, ReplacementDiagnostics)
    assert decision.diagnostics.total == 2
    assert decision.diagnostics.same_id == 1
    assert decision.diagnostics.bad_duration == 1
    assert decision.diagnostics.overused == 0
    assert decision.diagnostics.job_overused == 0


def test_only_current_asset_exists_reason() -> None:
    repo = FakeAssetRepository([_asset("a1")])
    decision = select_replacement(repo, "test", "intro", "a1")
    assert decision.chosen is None
    assert "only the current asset exists" in decision.reason


def test_no_assets_in_category_reason() -> None:
    repo = FakeAssetRepository([])
    decision = select_replacement(repo, "test", "intro", "a1")
    assert decision.chosen is None
    assert "no assets found" in decision.reason


def test_side_effect_free() -> None:
    """select_replacement must not mutate repository state."""
    assets = [_asset("a1"), _asset("alt1")]
    repo = FakeAssetRepository(assets)
    decision = select_replacement(repo, "test", "intro", "a1")
    assert decision.chosen is not None
    for a in assets:
        assert a.usage_count == 0
