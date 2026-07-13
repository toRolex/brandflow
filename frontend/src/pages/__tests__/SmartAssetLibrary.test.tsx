import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import SmartAssetLibrary from "../SmartAssetLibrary";
import { ProductProvider } from "../../ProductContext";
import { api } from "../../api/client";
import type { AssetRecord, AssetStats, CategoryItem, ProductConfig } from "../../types";

const mockAssets: AssetRecord[] = [
  {
    asset_id: "a1", file_path: "/workspace/shared_assets/indexed/longjing/brew/a1.mp4",
    category: "冲泡", product: "龙井茶", confidence: 0.9, duration_seconds: 5.0,
    status: "available", usage_count: 0, source_video: "v1.mp4", tags: [],
    created_at: "2025-01-01T00:00:00", last_used_at: "2025-01-01T00:00:00",
  },
  {
    asset_id: "a2", file_path: "/workspace/shared_assets/indexed/longjing/origin/a2.mp4",
    category: "产地", product: "龙井茶", confidence: 0.85, duration_seconds: 3.0,
    status: "available", usage_count: 2, source_video: "v1.mp4", tags: [],
    created_at: "2025-01-01T00:00:00", last_used_at: "2025-01-01T00:00:00",
  },
  {
    asset_id: "a3", file_path: "/workspace/shared_assets/indexed/puer/brew/a3.mp4",
    category: "冲泡", product: "普洱茶", confidence: 0.8, duration_seconds: 7.0,
    status: "available", usage_count: 0, source_video: "v2.mp4", tags: [],
    created_at: "2025-01-01T00:00:00", last_used_at: "2025-01-01T00:00:00",
  },
];

const mockStats: AssetStats = {
  total: 3, available: 3, disabled: 0, source_videos: 2,
};

const mockCategories: CategoryItem[] = [
  { id: "brew", name: "冲泡", description: "Brewing process" },
  { id: "origin", name: "产地", description: "Origin" },
  { id: "taste", name: "品鉴", description: "Tasting" },
];

const mockProducts = [
  { id: "prod_longjing", name: "龙井茶" },
  { id: "prod_puer", name: "普洱茶" },
];

function mockConfig(overrides: Partial<ProductConfig & { id?: string }> = {}): ProductConfig & { id?: string } {
  return {
    id: "prod_longjing",
    default_name: "龙井茶",
    default_brand: "",
    script: { scene: "", material: "", system_prompt: "" },
    categories: mockCategories.map(c => ({ ...c, vision_prompt: "" })),
    ...overrides,
  };
}

vi.mock("../../api/client", () => ({
  api: {
    listIndexedAssetsShared: vi.fn(),
    listIndexedAssets: vi.fn(),
    listCategories: vi.fn(),
    listProducts: vi.fn(),
    getProductConfig: vi.fn(),
    switchProduct: vi.fn(),
    updateAssetStatusShared: vi.fn(),
    updateAssetStatus: vi.fn(),
    updateAssetFields: vi.fn(),
    batchUpdateAssetFields: vi.fn(),
    deleteAssetShared: vi.fn(),
    batchDeleteAssets: vi.fn(),
    uploadAssetShared: vi.fn(),
    indexAssetsShared: vi.fn(),
  },
}));

describe("SmartAssetLibrary select-all features", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listIndexedAssetsShared).mockResolvedValue({ assets: mockAssets, stats: mockStats });
    vi.mocked(api.listCategories).mockResolvedValue(mockCategories);
    vi.mocked(api.listProducts).mockResolvedValue(mockProducts);
    vi.mocked(api.getProductConfig).mockResolvedValue(mockConfig());
    vi.mocked(api.switchProduct).mockResolvedValue({ active_product_id: "" });
    vi.mocked(api.updateAssetStatusShared).mockResolvedValue({ updated: 1 });
    vi.mocked(api.updateAssetFields).mockResolvedValue({ updated: 1 });
    vi.mocked(api.batchUpdateAssetFields).mockResolvedValue({ updated: 1 });
    vi.mocked(api.deleteAssetShared).mockResolvedValue({ status: "deleted" });
    vi.mocked(api.batchDeleteAssets).mockResolvedValue({ deleted: 1, files_deleted: 1 });
    vi.mocked(api.uploadAssetShared).mockResolvedValue({ name: "test.mp4", size_bytes: 1000, in_use: false });
    vi.mocked(api.indexAssetsShared).mockResolvedValue({ indexed: 1, skipped: 0, total_clips: 1 });
  });

  function renderLibrary() {
    return render(
      <ProductProvider>
        <SmartAssetLibrary />
      </ProductProvider>
    );
  }

  it("Seam 1: 过滤区渲染'全选当前筛选结果'按钮", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(api.listIndexedAssetsShared).toHaveBeenCalled();
    });

    // The select-all button should be in the document when filtered assets exist
    await waitFor(() => {
      expect(screen.getByText("全选当前筛选结果")).toBeInTheDocument();
    });
  });

  it("Seam 2: 点击'全选当前筛选结果'选中所有可见素材", async () => {
    renderLibrary();

    // Wait for product filter to take effect (shows 2 of 3 assets)
    await waitFor(() => {
      expect(screen.getByText("共 2 / 3 条素材")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("全选当前筛选结果"));

    // BatchActionBar should appear with count 2
    await waitFor(() => {
      expect(screen.getByText("已选择 2 张卡片")).toBeInTheDocument();
    });
  });

  it("Seam 3: 全选后按钮变为'取消全选'，再次点击清除选择", async () => {
    renderLibrary();

    // Wait for product filter to take effect
    await waitFor(() => {
      expect(screen.getByText("共 2 / 3 条素材")).toBeInTheDocument();
    });

    // Click select-all
    fireEvent.click(screen.getByText("全选当前筛选结果"));

    // Button text should change to "取消全选"
    await waitFor(() => {
      expect(screen.getByText("取消全选")).toBeInTheDocument();
    });

    // Click again to deselect
    fireEvent.click(screen.getByText("取消全选"));

    // BatchActionBar should disappear
    await waitFor(() => {
      expect(screen.queryByText(/已选择/)).not.toBeInTheDocument();
    });

    // Button text should revert to "全选当前筛选结果"
    expect(screen.getByText("全选当前筛选结果")).toBeInTheDocument();
  });

  it("Seam 4: 选中后出现'清空选择'按钮，点击清除所有选择", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(api.listIndexedAssetsShared).toHaveBeenCalled();
    });

    // Click select-all
    fireEvent.click(screen.getByText("全选当前筛选结果"));

    // "清空选择" button should appear
    await waitFor(() => {
      expect(screen.getByText("清空选择")).toBeInTheDocument();
    });

    // Click clear
    fireEvent.click(screen.getByText("清空选择"));

    // Both BatchActionBar and selection controls should show no selection
    await waitFor(() => {
      expect(screen.queryByText(/已选择/)).not.toBeInTheDocument();
    });
  });

  it("Seam 5: 全选只选中当前筛选结果（非全部素材）", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(api.listIndexedAssetsShared).toHaveBeenCalled();
    });

    // Filter by category "产地" — only a2 matches
    const selects = screen.getAllByRole("combobox");
    const catSelect = selects[1]; // category select is the second combobox
    fireEvent.change(catSelect, { target: { value: "产地" } });

    // Click select-all
    await waitFor(() => {
      expect(screen.getByText("全选当前筛选结果")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("全选当前筛选结果"));

    // Only 1 asset (a2, category: 产地) should be selected
    await waitFor(() => {
      expect(screen.getByText("已选择 1 张卡片")).toBeInTheDocument();
    });
  });

  it("Seam 6: 已选数量实时显示在过滤区", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(api.listIndexedAssetsShared).toHaveBeenCalled();
    });

    // Initially no selected count should be visible (no selection yet)
    expect(screen.queryByText(/已选/)).not.toBeInTheDocument();

    // Select one asset via grid click
    await waitFor(() => {
      expect(screen.getByText("a1.mp4")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("a1.mp4"));

    // Now selected count should be visible in the filter area
    await waitFor(() => {
      expect(screen.getByText("已选 1 项")).toBeInTheDocument();
    });
  });
});

describe("SmartAssetLibrary product filtering", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listIndexedAssetsShared).mockResolvedValue({ assets: mockAssets, stats: mockStats });
    vi.mocked(api.listCategories).mockResolvedValue(mockCategories);
    vi.mocked(api.listProducts).mockResolvedValue(mockProducts);
    vi.mocked(api.getProductConfig).mockResolvedValue(mockConfig());
    vi.mocked(api.switchProduct).mockResolvedValue({ active_product_id: "" });
    vi.mocked(api.updateAssetStatusShared).mockResolvedValue({ updated: 1 });
    vi.mocked(api.updateAssetFields).mockResolvedValue({ updated: 1 });
    vi.mocked(api.batchUpdateAssetFields).mockResolvedValue({ updated: 1 });
    vi.mocked(api.deleteAssetShared).mockResolvedValue({ status: "deleted" });
    vi.mocked(api.batchDeleteAssets).mockResolvedValue({ deleted: 1, files_deleted: 1 });
    vi.mocked(api.uploadAssetShared).mockResolvedValue({ name: "test.mp4", size_bytes: 1000, in_use: false });
    vi.mocked(api.indexAssetsShared).mockResolvedValue({ indexed: 1, skipped: 0, total_clips: 1 });
  });

  function renderLibrary() {
    return render(
      <ProductProvider>
        <SmartAssetLibrary />
      </ProductProvider>
    );
  }

  it("默认筛选当前活跃产品", async () => {
    renderLibrary();

    // Product context loads and SmartAssetLibrary fetches categories
    await waitFor(() => {
      expect(api.listCategories).toHaveBeenCalled();
    });

    // Categories configured for the active product (龙井茶) should be displayed
    // Use exact text with count to avoid matching asset card badges
    await waitFor(() => {
      expect(screen.getByText("冲泡 (1)")).toBeInTheDocument();
      expect(screen.getByText("产地 (1)")).toBeInTheDocument();
      expect(screen.getByText("品鉴 (0)")).toBeInTheDocument();
    });
  });

  it("可切换产品筛选", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(screen.getByText("龙井茶")).toBeInTheDocument();
    });

    // Find the product select (first combobox)
    const selects = screen.getAllByRole("combobox");
    const prodSelect = selects[0];
    fireEvent.change(prodSelect, { target: { value: "普洱茶" } });

    // Should re-fetch assets with new product filter
    await waitFor(() => {
      expect(api.listIndexedAssetsShared).toHaveBeenCalled();
    });
  });

  it("素材列表按产品筛选", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(api.listIndexedAssetsShared).toHaveBeenCalled();
    });

    // With product filter set to 龙井茶 (default active), filtered assets should
    // only show 龙井茶 assets (a1, a2), not 普洱茶 (a3)
    await waitFor(() => {
      expect(screen.getByText("共 2 / 3 条素材")).toBeInTheDocument();
    });
  });

  it("分类下拉来自当前产品配置分类，含零计数", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(api.listCategories).toHaveBeenCalled();
    });

    // All configured categories should appear in the select, including "品鉴" with count 0
    await waitFor(() => {
      expect(screen.getByText("冲泡 (1)")).toBeInTheDocument();
      expect(screen.getByText("产地 (1)")).toBeInTheDocument();
      expect(screen.getByText("品鉴 (0)")).toBeInTheDocument();
    });
  });

  it("分类计数基于当前产品筛选后的素材集合", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(screen.getByText("冲泡 (1)")).toBeInTheDocument();
    });

    // Switch to 普洱茶 - should only count 普洱茶 assets
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "普洱茶" } });

    await waitFor(() => {
      // 普洱茶 has 1 asset in category "冲泡"
      expect(screen.getByText("冲泡 (1)")).toBeInTheDocument();
      expect(screen.getByText("品鉴 (0)")).toBeInTheDocument();
    });
  });

  it("批量编辑和素材预览使用同一套分类选项", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(api.listCategories).toHaveBeenCalled();
    });

    // Select an asset by clicking its card (AssetGrid uses divs with onClick, not checkboxes)
    await waitFor(() => {
      expect(screen.getByText("a1.mp4")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("a1.mp4"));

    // BatchActionBar should be visible with selected count
    await waitFor(() => {
      expect(screen.getByText(/已选择/)).toBeInTheDocument();
    });

    // Click "批量编辑" to see the category dropdown
    const batchEditBtn = screen.getByText("批量编辑");
    fireEvent.click(batchEditBtn);

    // All configured categories should appear in the batch edit dropdown
    await waitFor(() => {
      // "冲泡" appears in: filter dropdown, asset badge, and batch edit dropdown
      const categoryOptions = screen.getAllByText("冲泡");
      expect(categoryOptions.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("产品无分类时回退到实例级分类或默认分类", async () => {
    // getProductConfig returns config without product-level categories
    vi.mocked(api.getProductConfig).mockResolvedValue(
      mockConfig({ categories: undefined })
    );

    renderLibrary();

    // listCategories still returns instance-level/default categories
    await waitFor(() => {
      expect(api.listCategories).toHaveBeenCalled();
    });

    // Categories from the API should still be displayed
    await waitFor(() => {
      expect(screen.getByText("冲泡 (1)")).toBeInTheDocument();
    });
  });
});

describe("unmapped/historical categories (#124)", () => {
  const mockAssetsWithUnmapped: AssetRecord[] = [
    ...mockAssets,
    {
      asset_id: "a4",
      file_path: "/workspace/shared_assets/indexed/longjing/legacy/a4.mp4",
      category: "旧分类",
      product: "龙井茶",
      confidence: 0.7,
      duration_seconds: 4.0,
      status: "available",
      usage_count: 0,
      source_video: "v3.mp4",
      tags: [],
      created_at: "2025-01-01T00:00:00",
      last_used_at: "2025-01-01T00:00:00",
    },
  ];

  function renderLibrary() {
    return render(
      <ProductProvider>
        <SmartAssetLibrary />
      </ProductProvider>
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listIndexedAssetsShared).mockResolvedValue({
      assets: mockAssetsWithUnmapped,
      stats: { total: 4, available: 4, disabled: 0, source_videos: 3 },
    });
    vi.mocked(api.listCategories).mockResolvedValue(mockCategories);
    vi.mocked(api.listProducts).mockResolvedValue(mockProducts);
    vi.mocked(api.getProductConfig).mockResolvedValue(mockConfig());
    vi.mocked(api.switchProduct).mockResolvedValue({ active_product_id: "" });
    vi.mocked(api.updateAssetStatusShared).mockResolvedValue({ updated: 1 });
    vi.mocked(api.updateAssetFields).mockResolvedValue({ updated: 1 });
    vi.mocked(api.batchUpdateAssetFields).mockResolvedValue({ updated: 1 });
    vi.mocked(api.deleteAssetShared).mockResolvedValue({ status: "deleted" });
    vi.mocked(api.batchDeleteAssets).mockResolvedValue({ deleted: 1, files_deleted: 1 });
    vi.mocked(api.uploadAssetShared).mockResolvedValue({ name: "test.mp4", size_bytes: 1000, in_use: false });
    vi.mocked(api.indexAssetsShared).mockResolvedValue({ indexed: 1, skipped: 0, total_clips: 1 });
  });

  it("未映射分类显示在下拉列表中，与配置分类并列且可区分", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(api.listCategories).toHaveBeenCalled();
    });

    // productFilteredAssets (龙井茶 active) = [a1, a2, a4]
    // Configured categories: 冲泡 (1), 产地 (1), 品鉴 (0)
    // Unmapped category: 旧分类 (1)
    await waitFor(() => {
      expect(screen.getByText("冲泡 (1)")).toBeInTheDocument();
      expect(screen.getByText("产地 (1)")).toBeInTheDocument();
      expect(screen.getByText("品鉴 (0)")).toBeInTheDocument();
    });

    // Unmapped category should appear with correct count
    expect(screen.getByText("旧分类 (1)")).toBeInTheDocument();
    // Separator text should exist
    expect(screen.getByText(/未映射/)).toBeInTheDocument();
  });

  it("选择未映射分类正确筛选素材", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(screen.getByText("旧分类 (1)")).toBeInTheDocument();
    });

    const selects = screen.getAllByRole("combobox");
    const catSelect = selects[1];
    fireEvent.change(catSelect, { target: { value: "旧分类" } });

    await waitFor(() => {
      // Only a4 (旧分类) should be shown, total assets = 4
      expect(screen.getByText("共 1 / 4 条素材")).toBeInTheDocument();
      expect(screen.getByText("a4.mp4")).toBeInTheDocument();
    });
  });

  it("全部分类计数与各分类计数来源一致", async () => {
    renderLibrary();

    // productFilteredAssets (龙井茶 active) = [a1, a2, a4] = 3 items
    await waitFor(() => {
      expect(screen.getByText("全部分类 (3)")).toBeInTheDocument();
    });
  });

  it("切换产品时未映射分类基于目标产品重新计算", async () => {
    renderLibrary();

    await waitFor(() => {
      expect(screen.getByText("旧分类 (1)")).toBeInTheDocument();
    });

    // Switch to 普洱茶
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "普洱茶" } });

    // 普洱茶 only has a3 (冲泡), no unmapped assets
    await waitFor(() => {
      expect(screen.getByText("全部分类 (1)")).toBeInTheDocument();
      // Unmapped separator should be gone since 普洱茶 has no unmapped categories
      expect(screen.queryByText(/未映射/)).not.toBeInTheDocument();
    });
  });
});
