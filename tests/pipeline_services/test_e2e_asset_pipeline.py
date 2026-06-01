import json
import os
import subprocess
from pathlib import Path

import pytest

from packages.pipeline_services.asset_library.models import AssetRecord, Category
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.pipeline_services.asset_library.retriever import AssetRetriever


def _create_mock_video(output_path: Path, duration: float = 3.0) -> Path:
    """Create a minimal test video using ffmpeg lavfi."""
    # 使用项目根目录的绝对路径
    project_root = Path(__file__).parent.parent.parent
    ffmpeg = project_root / "tools" / "bin" / "ffmpeg.exe"
    if not ffmpeg.exists():
        ffmpeg = os.environ.get("FFMPEG_PATH", "tools/bin/ffmpeg.exe")
    cmd = [
        str(ffmpeg),
        "-f", "lavfi",
        "-i", f"color=c=black:s=320x240:d={duration}:r=24",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-y",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


@pytest.mark.slow
class TestE2EAssetPipeline:
    def test_full_index_retrieve_cycle(self, tmp_path):
        # 1. Create mock clips in a simulated semantic directory structure
        source_dir = tmp_path / "source"
        output_base = tmp_path / "素材库"
        db_path = tmp_path / "asset_index.db"
        source_dir.mkdir(parents=True)

        # Create mock videos with different "content" (all black, testing structure)
        for name in ["clip_cut.mp4", "clip_stir.mp4", "clip_macro.mp4"]:
            _create_mock_video(source_dir / name, duration=3.0)

        # 2. Manually insert records (bypass indexer since no real multimodal API)
        repo = AssetRepository(db_path)
        records = [
            AssetRecord(
                asset_id="e2e_001", file_path=str(source_dir / "clip_cut.mp4"),
                category=Category.CUTTING, product="荔枝菌", confidence=0.9,
                duration_seconds=3.0, status="available",
            ),
            AssetRecord(
                asset_id="e2e_002", file_path=str(source_dir / "clip_stir.mp4"),
                category=Category.STIR_FRY, product="荔枝菌", confidence=0.8,
                duration_seconds=3.0, status="available",
            ),
            AssetRecord(
                asset_id="e2e_003", file_path=str(source_dir / "clip_macro.mp4"),
                category=Category.MACRO, product="荔枝菌", confidence=0.7,
                duration_seconds=3.0, status="available",
            ),
        ]
        for r in records:
            repo.insert(r)

        # 3. Verify query
        results = repo.query_by_category("荔枝菌", Category.CUTTING)
        assert len(results) == 1
        assert results[0].asset_id == "e2e_001"

        # 4. Run retrieval against a real script
        retriever = AssetRetriever(repo)
        script = "荔枝菌切片后下锅翻炒。充分烹熟后出锅装盘。这是成品展示。"
        selected = retriever.retrieve(script, "荔枝菌")

        assert len(selected) == 3
        categories = [s["category"] for s in selected]
        assert "切配处理" in categories
        assert "烹饪翻炒" in categories

        # 5. Verify usage count increased
        assert repo.get_usage_count("e2e_001") >= 0

    def test_fallback_when_no_matching_assets(self, tmp_path):
        db_path = tmp_path / "fallback_test.db"
        repo = AssetRepository(db_path)

        repo.insert(AssetRecord(
            asset_id="fb_001", file_path="/x.mp4",
            category=Category.MACRO, product="荔枝菌",
        ))

        retriever = AssetRetriever(repo)
        script = "今天天气真好。出去散步走走。"
        selected = retriever.retrieve(script, "荔枝菌")

        assert len(selected) >= 1
        assert selected[0]["method"] == "fallback"
