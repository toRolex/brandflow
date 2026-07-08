import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import SmartAssetLibrary from "../SmartAssetLibrary";
import { api } from "../../api/client";
import type { AssetRecord, AssetStats } from "../../types";

vi.mock("../../api/client", () => ({
  api: {
    listIndexedAssetsShared: vi.fn(),
    listCategories: vi.fn(),
    updateAssetStatusShared: vi.fn(),
    updateAssetFields: vi.fn(),
    batchUpdateAssetFields: vi.fn(),
    batchDeleteAssets: vi.fn(),
    deleteAssetShared: vi.fn(),
    uploadAssetShared: vi.fn(),
    indexAssetsSharedAsync: vi.fn(),
    getIndexStatus: vi.fn(),
  },
}));

const MOCK_ASSETS: AssetRecord[] = [
  {
    asset_id: "asset_001",
    file_path: "/workspace/shared_assets/indexed/荔枝菌/产品特写/a.mp4",
    category: "产品特写",
    product: "荔枝菌",
    confidence: 0.9,
    duration_seconds: 5.0,
    status: "available" as const,
    usage_count: 2,
    source_video: "",
    tags: ["tag1"],
    created_at: "2025-01-01T00:00:00Z",
    last_used_at: "",
  },
  {
    asset_id: "asset_002",
    file_path: "/workspace/shared_assets/indexed/荔枝菌/烹饪翻炒/b.mp4",
    category: "烹饪翻炒",
    product: "荔枝菌",
    confidence: 0.8,
    duration_seconds: 3.0,
    status: "available" as const,
    usage_count: 1,
    source_video: "",
    tags: [],
    created_at: "2025-01-02T00:00:00Z",
    last_used_at: "",
  },
];

const MOCK_STATS: AssetStats = {
  total: 2,
  available: 2,
  disabled: 0,
  source_videos: 0,
};

const MOCK_CONFIG_CATEGORIES = [
  { id: "promo", name: "促销活动", description: "" },
  { id: "unboxing", name: "开箱展示", description: "" },
  { id: "product_review", name: "产品评测", description: "" },
];

describe("SmartAssetLibrary - categories from API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listIndexedAssetsShared).mockResolvedValue({
      assets: MOCK_ASSETS,
      stats: MOCK_STATS,
    });
    vi.mocked(api.listCategories).mockResolvedValue(MOCK_CONFIG_CATEGORIES);
  });

  it("loads and uses API categories alongside existing asset categories", async () => {
    render(<SmartAssetLibrary />);

    // Wait for categories to appear in the filter dropdown (count text format: "name (count)")
    await screen.findByText(/促销活动/);
    screen.getByText(/开箱展示/);
    screen.getByText(/产品评测/);

    // Existing asset categories should also appear
    const teXieElements = screen.getAllByText(/产品特写/);
    expect(teXieElements.length).toBeGreaterThan(0);
    const stirFryElements = screen.getAllByText(/烹饪翻炒/);
    expect(stirFryElements.length).toBeGreaterThan(0);
  });

  it("calls listCategories on mount", async () => {
    render(<SmartAssetLibrary />);

    expect(api.listCategories).toHaveBeenCalledTimes(1);
  });
});
