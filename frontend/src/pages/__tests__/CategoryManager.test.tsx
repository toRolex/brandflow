import { describe, it, expect, vi, beforeEach } from "vitest";
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
  { name: "产品展示", description: "产品特写和展示镜头", vision_prompt: "product showcase close-up" },
  { name: "前期准备", description: "产品前期的整理、检查等准备过程", vision_prompt: "preparation inspection organization" },
  { name: "制作过程", description: "产品的加工和制作过程", vision_prompt: "production manufacturing process" },
];

const DEFAULT_CONFIG = {
  default_name: "示例产品",
  default_brand: "示例品牌",
  script: { scene: "", material: "", system_prompt: "" },
  categories: MOCK_CATEGORIES,
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
        { name: "成品出锅", description: "最终成品展示", vision_prompt: "final dish plating" },
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
      { name: "产品细节", description: "产品特写", vision_prompt: "product display" },
      { name: "调味过程", description: "加入调料", vision_prompt: "seasoning process" },
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
        { name: "产品展示编辑", description: "修改后描述", vision_prompt: "modified prompt" },
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
