import type {
  AssetCategory,
  AssetRecord,
  AssetStats,
  IndexResult,
  IndexStatus,
} from "./index";

function assertType<T>(_value: T): void {}

const category: AssetCategory = "产地溯源";
const indexStatus: IndexStatus = "processing";

assertType<AssetRecord>({
  asset_id: "asset_001",
  file_path: "/clips/asset_001.mp4",
  category,
  product: "见手青",
  confidence: 0.95,
  duration_seconds: 5,
  status: "available",
  usage_count: 1,
  source_video: "source.mp4",
  tags: ["采摘", "松林"],
  created_at: "2026-05-28T14:30:00Z",
  last_used_at: "2026-05-29T08:00:00Z",
});

assertType<AssetStats>({
  total_clips: 12,
  available_clips: 10,
  disabled_clips: 2,
  source_videos: 3,
});

assertType<IndexResult>({
  indexed: 2,
  skipped: 1,
  total_clips: 8,
});

assertType<IndexStatus>(indexStatus);
