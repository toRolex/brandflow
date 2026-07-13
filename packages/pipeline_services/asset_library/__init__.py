"""Asset library — semantic clip indexing and retrieval."""

from packages.pipeline_services.asset_library.category_config import (
    CategoryConfig,
    default_categories,
    get_categories,
)
from packages.pipeline_services.asset_library.models import (
    AssetRecord,
    AssetStatus,
    Category,  # Deprecated: use CategoryConfig for new code
    load_keyword_map,
)
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.pipeline_services.asset_library.indexer import AssetIndexer
from packages.pipeline_services.asset_library.retriever import AssetRetriever

__all__ = [
    "AssetIndexer",
    "AssetRetriever",
    "AssetRepository",
    "AssetRecord",
    "AssetStatus",
    "Category",
    "CategoryConfig",
    "default_categories",
    "load_keyword_map",
    "get_categories",
]
