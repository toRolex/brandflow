import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import CategoryManager from "../CategoryManager";
import { api } from "../../api/client";

vi.mock("../../api/client", () => ({
  api: {
    getProductConfig: vi.fn(),
    saveProductConfig: vi.fn(),
    suggestCategories: vi.fn(),
  },
}));

const MOCK_CATEGORIES = [
  { id: "chanpinzhanshi", name: "产品展示", description: "产品特写和展示镜头", vision_prompt: "product showcase close-up" },
  { id: "qianqizhunbei", name: "前期准备", description: "产品前期的整理、检查等准备过程", vision_prompt: "preparation inspection organization" },
  { id: "zhizuoguocheng", name: "制作过程", description: "产品的加工和制作过程", vision_prompt: "production manufacturing process" },
];

const DEFAULT_CONFIG = {
  default_name: "示例产品",
  default_brand: "示例品牌",
  script: { scene: "", material: "", system_prompt: "" },
  categories: [...MOCK_CATEGORIES],
};

describe("CategoryManager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getProductConfig).mockResolvedValue(DEFAULT_CONFIG);
  });

  it("加载时调用 API 并展示分类列表", async () => {
    render(<CategoryManager />);
    expect(api.getProductConfig).toHaveBeenCalledTimes(1);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });
    expect(screen.getByText("前期准备")).toBeInTheDocument();
    expect(screen.getByText("制作过程")).toBeInTheDocument();
  });

  it("空分类列表显示空状态提示", async () => {
    vi.mocked(api.getProductConfig).mockResolvedValue({
      ...DEFAULT_CONFIG,
      categories: [],
    });
    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("暂无分类")).toBeInTheDocument();
    });
  });

  it("加载失败时显示错误提示", async () => {
    vi.mocked(api.getProductConfig).mockRejectedValue(new Error("Network Error"));
    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("加载分类失败")).toBeInTheDocument();
    });
  });

  it("新增分类按钮打开表单", async () => {
    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const addBtn = screen.getByText("新增分类");
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText("分类名称")).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText("分类描述")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Vision prompt")).toBeInTheDocument();
  });

  it("新增分类表单验证必填字段", async () => {
    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const addBtn = screen.getByText("新增分类");
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText("分类名称")).toBeInTheDocument();
    });

    const confirmBtn = screen.getByText("确认");
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText("分类名称不能为空")).toBeInTheDocument();
    });
  });

  it("新增分类后保存到配置", async () => {
    vi.mocked(api.saveProductConfig).mockResolvedValue({
      ...DEFAULT_CONFIG,
      categories: [
        ...MOCK_CATEGORIES,
        { id: "chengpinchuguo", name: "成品出锅", description: "最终成品展示", vision_prompt: "final dish plating" },
      ],
    });

    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const addBtn = screen.getByText("新增分类");
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText("分类名称")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("分类名称"), {
      target: { value: "成品出锅" },
    });
    fireEvent.change(screen.getByPlaceholderText("分类描述"), {
      target: { value: "最终成品展示" },
    });
    fireEvent.change(screen.getByPlaceholderText("Vision prompt"), {
      target: { value: "final dish plating" },
    });

    const confirmBtn = screen.getByText("确认");
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });
  });

  it("删除分类按钮移除分类", async () => {
    vi.mocked(api.saveProductConfig).mockResolvedValue({
      ...DEFAULT_CONFIG,
      categories: [MOCK_CATEGORIES[1], MOCK_CATEGORIES[2]],
    });

    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByText("删除");
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });
  });

  it("AI 建议按钮调用 suggest API", async () => {
    vi.mocked(api.suggestCategories).mockResolvedValue({
      suggestions: [
        { label: "产品细节", description: "产品特写", vision_prompt: "product display" },
        { label: "调味过程", description: "加入调料", vision_prompt: "seasoning process" },
      ],
    });

    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const aiBtn = screen.getByText("AI 建议");
    fireEvent.click(aiBtn);

    await waitFor(() => {
      expect(api.suggestCategories).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(screen.getByText("产品细节")).toBeInTheDocument();
    });
    expect(screen.getByText("调味过程")).toBeInTheDocument();
  });

  it("AI 建议可勾选后确认添加", async () => {
    vi.mocked(api.suggestCategories).mockResolvedValue({
      suggestions: [
        { label: "产品细节", description: "产品特写", vision_prompt: "product display" },
        { label: "调味过程", description: "加入调料", vision_prompt: "seasoning process" },
      ],
    });

    const updatedCategories = [
      ...MOCK_CATEGORIES,
      { id: "chanpinxijie", name: "产品细节", description: "产品特写", vision_prompt: "product display" },
      { id: "tiaoweiguocheng", name: "调味过程", description: "加入调料", vision_prompt: "seasoning process" },
    ];
    vi.mocked(api.saveProductConfig).mockResolvedValue({
      ...DEFAULT_CONFIG,
      categories: updatedCategories,
    });

    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const aiBtn = screen.getByText("AI 建议");
    fireEvent.click(aiBtn);

    // Wait for suggestions to appear
    await waitFor(() => {
      expect(screen.getByText("产品细节")).toBeInTheDocument();
    });

    // Click confirm to add all selected suggestions (they should be checked by default)
    const confirmBtn = screen.getByText("确认添加");
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });
  });

  it("保存失败时显示错误提示", async () => {
    vi.mocked(api.saveProductConfig).mockRejectedValue(new Error("Save failed"));

    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByText("删除");
    fireEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("保存失败")).toBeInTheDocument();
    });
  });

  it("页面标题正确显示", async () => {
    render(<CategoryManager />);
    await waitFor(() => {
      expect(screen.getByText("素材分类")).toBeInTheDocument();
    });
  });

  it("编辑分类按钮打开预填表单", async () => {
    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText("编辑");
    fireEvent.click(editButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("编辑分类")).toBeInTheDocument();
    });

    const nameInput = screen.getByPlaceholderText("分类名称") as HTMLInputElement;
    expect(nameInput.value).toBe("产品展示");

    const descInput = screen.getByPlaceholderText("分类描述") as HTMLInputElement;
    expect(descInput.value).toBe("产品特写和展示镜头");

    const promptInput = screen.getByPlaceholderText("Vision prompt") as HTMLInputElement;
    expect(promptInput.value).toBe("product showcase close-up");
  });

  it("编辑分类后保存更新到配置", async () => {
    vi.mocked(api.saveProductConfig).mockResolvedValue({
      ...DEFAULT_CONFIG,
      categories: [
        { id: "chanpinzhanshi", name: "产品展示编辑", description: "修改后描述", vision_prompt: "modified prompt" },
        MOCK_CATEGORIES[1],
        MOCK_CATEGORIES[2],
      ],
    });

    render(<CategoryManager />);

    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText("编辑");
    fireEvent.click(editButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("编辑分类")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("分类名称"), {
      target: { value: "产品展示编辑" },
    });
    fireEvent.change(screen.getByPlaceholderText("分类描述"), {
      target: { value: "修改后描述" },
    });
    fireEvent.change(screen.getByPlaceholderText("Vision prompt"), {
      target: { value: "modified prompt" },
    });

    const confirmBtn = screen.getByText("确认");
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });
  });
});

// ── S6-S9: id generation, preservation, and stable key ──

describe("CategoryManager - id handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getProductConfig).mockResolvedValue(DEFAULT_CONFIG);
  });

  // S6: auto-generate id on add
  it("S6: 新增分类时自动生成非空 id", async () => {
    let savedPayload: unknown = null;
    vi.mocked(api.saveProductConfig).mockImplementation(async (payload) => {
      savedPayload = payload;
      return { ...DEFAULT_CONFIG, categories: payload.categories };
    });

    render(<CategoryManager />);
    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("新增分类"));
    await waitFor(() => {
      expect(screen.getByPlaceholderText("分类名称")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("分类名称"), {
      target: { value: "Test Category" },
    });

    fireEvent.click(screen.getByText("确认"));

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });

    const categories = (savedPayload as { categories?: Array<{ id: string }> })?.categories ?? [];
    const newCat = categories[categories.length - 1];
    expect(newCat.id).toBeTruthy();
    expect(newCat.id).toBe("test_category");
  });

  // S6: id is unique within same product
  it("S6: 新增分类的 id 在同产品内唯一（不同名生成不同 id）", async () => {
    let savedPayload: unknown = null;
    vi.mocked(api.saveProductConfig).mockImplementation(async (payload) => {
      savedPayload = payload;
      return { ...DEFAULT_CONFIG, categories: payload.categories };
    });

    render(<CategoryManager />);
    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("新增分类"));
    await waitFor(() => {
      expect(screen.getByPlaceholderText("分类名称")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("分类名称"), {
      target: { value: "New Category" },
    });

    fireEvent.click(screen.getByText("确认"));

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });

    const categories = (savedPayload as { categories?: Array<{ id: string }> })?.categories ?? [];
    const newCat = categories[categories.length - 1];
    expect(newCat.id).toBe("new_category");
    // Should not conflict with existing MOCK_CATEGORIES ids
    const existingIds = MOCK_CATEGORIES.map(c => c.id);
    expect(existingIds).not.toContain(newCat.id);
  });

  // S7: edit preserves id
  it("S7: 编辑分类名称不改变已有 id", async () => {
    let savedPayload: unknown = null;
    vi.mocked(api.saveProductConfig).mockImplementation(async (payload) => {
      savedPayload = payload;
      return { ...DEFAULT_CONFIG, categories: payload.categories };
    });

    render(<CategoryManager />);
    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    // Click edit on first category
    const editButtons = screen.getAllByText("编辑");
    fireEvent.click(editButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("编辑分类")).toBeInTheDocument();
    });

    // Change the name but keep same id
    const nameInput = screen.getByPlaceholderText("分类名称");
    fireEvent.change(nameInput, {
      target: { value: "产品展示重命名" },
    });

    fireEvent.click(screen.getByText("确认"));

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });

    const categories = (savedPayload as { categories?: Array<{ id: string; name: string }> })?.categories ?? [];
    const editedCat = categories[0];
    // id stays the same (original was "chanpinzhanshi")
    expect(editedCat.id).toBe("chanpinzhanshi");
    // name changed
    expect(editedCat.name).toBe("产品展示重命名");
  });

  // S7: edit without changing name preserves id
  it("S7: 编辑分类仅改描述不改变已有 id", async () => {
    let savedPayload: unknown = null;
    vi.mocked(api.saveProductConfig).mockImplementation(async (payload) => {
      savedPayload = payload;
      return { ...DEFAULT_CONFIG, categories: payload.categories };
    });

    render(<CategoryManager />);
    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText("编辑");
    fireEvent.click(editButtons[1]); // "前期准备"

    await waitFor(() => {
      expect(screen.getByText("编辑分类")).toBeInTheDocument();
    });

    // Only change description
    const descInput = screen.getByPlaceholderText("分类描述");
    fireEvent.change(descInput, {
      target: { value: "新的描述" },
    });

    fireEvent.click(screen.getByText("确认"));

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });

    const categories = (savedPayload as { categories?: Array<{ id: string; name: string }> })?.categories ?? [];
    const editedCat = categories[1];
    expect(editedCat.id).toBe("qianqizhunbei");
    expect(editedCat.name).toBe("前期准备");
  });

  // S8: React key uses id
  it("S8: 分类列表以 id 为 React key", async () => {
    render(<CategoryManager />);
    await waitFor(() => {
      expect(screen.getByText("产品展示")).toBeInTheDocument();
    });

    // Check each row is rendered with data matching its id
    const rows = screen.getAllByRole("row");
    // header row + 3 data rows
    expect(rows).toHaveLength(4);

    // First data row has "产品展示"
    expect(rows[1].textContent).toContain("产品展示");
    // Second data row has "前期准备"
    expect(rows[2].textContent).toContain("前期准备");
    // Third data row has "制作过程"
    expect(rows[3].textContent).toContain("制作过程");
  });

  // S9: Chinese name generates non-empty id
  it("S9: 中文分类名生成非空 id", async () => {
    let savedPayload: unknown = null;
    vi.mocked(api.saveProductConfig).mockImplementation(async (payload) => {
      savedPayload = payload;
      return { ...DEFAULT_CONFIG, categories: payload.categories };
    });

    vi.mocked(api.getProductConfig).mockResolvedValue({
      ...DEFAULT_CONFIG,
      categories: [],
    });

    render(<CategoryManager />);
    await waitFor(() => {
      expect(screen.getByText("暂无分类")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("新增分类"));
    await waitFor(() => {
      expect(screen.getByPlaceholderText("分类名称")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("分类名称"), {
      target: { value: "产地溯源" },
    });

    fireEvent.click(screen.getByText("确认"));

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });

    const categories = (savedPayload as { categories?: Array<{ id: string }> })?.categories ?? [];
    const newCat = categories[0];
    // Must not be empty
    expect(newCat.id).toBeTruthy();
    expect(newCat.id.length).toBeGreaterThan(0);
    // Chinese-only name: expect a fallback id starting with "cat_"
    expect(newCat.id).toMatch(/^cat_/);
  });

  // S9: mixed Chinese-English generates valid id
  it("S9: 中英混合分类名生成有效 id", async () => {
    let savedPayload: unknown = null;
    vi.mocked(api.saveProductConfig).mockImplementation(async (payload) => {
      savedPayload = payload;
      return { ...DEFAULT_CONFIG, categories: payload.categories };
    });

    vi.mocked(api.getProductConfig).mockResolvedValue({
      ...DEFAULT_CONFIG,
      categories: [],
    });

    render(<CategoryManager />);
    await waitFor(() => {
      expect(screen.getByText("暂无分类")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("新增分类"));
    await waitFor(() => {
      expect(screen.getByPlaceholderText("分类名称")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("分类名称"), {
      target: { value: "产品ABC展示" },
    });

    fireEvent.click(screen.getByText("确认"));

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });

    const categories = (savedPayload as { categories?: Array<{ id: string }> })?.categories ?? [];
    const newCat = categories[0];
    expect(newCat.id).toBeTruthy();
    expect(newCat.id.length).toBeGreaterThan(0);
    // Should contain the ASCII parts
    expect(newCat.id).toContain("abc");
  });

  // AI suggestions generate id from label
  it("S9: AI 建议确认时从 label 生成非空 id", async () => {
    let savedPayload: unknown = null;
    vi.mocked(api.saveProductConfig).mockImplementation(async (payload) => {
      savedPayload = payload;
      return { ...DEFAULT_CONFIG, categories: payload.categories };
    });

    vi.mocked(api.suggestCategories).mockResolvedValue({
      suggestions: [
        { label: "纯中文名称", description: "测试", vision_prompt: "test" },
      ],
    });

    vi.mocked(api.getProductConfig).mockResolvedValue({
      ...DEFAULT_CONFIG,
      categories: [],
    });

    render(<CategoryManager />);
    await waitFor(() => {
      expect(screen.getByText("暂无分类")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("AI 建议"));

    await waitFor(() => {
      expect(screen.getByText("纯中文名称")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("确认添加"));

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
    });

    const categories = (savedPayload as { categories?: Array<{ id: string }> })?.categories ?? [];
    const newCat = categories[0];
    expect(newCat.id).toBeTruthy();
    expect(newCat.id.length).toBeGreaterThan(0);
  });
});
