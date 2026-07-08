import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { ProductProvider } from "../ProductContext";
import ProductConfigForm from "../pages/ProductConfigForm";
import { api } from "../api/client";
import type { ProductConfig } from "../types";

const mockProductConfig = (overrides: Partial<ProductConfig & { id?: string; name?: string }> = {}): ProductConfig & { id?: string; name?: string } => ({
  id: "prod_a",
  name: "产品 A",
  default_name: "产品 A",
  default_brand: "品牌 A",
  script: {
    scene: "",
    material: "",
    system_prompt: "",
  },
  ...overrides,
});

vi.mock("../api/client", () => ({
  api: {
    listProducts: vi.fn(),
    getProductConfig: vi.fn(),
    getProductConfigById: vi.fn(),
    saveProductConfig: vi.fn(),
    saveProductConfigById: vi.fn(),
    resetProductConfig: vi.fn(),
    switchProduct: vi.fn(),
  },
}));

function renderForm() {
  return render(
    <ProductProvider>
      <ProductConfigForm />
    </ProductProvider>
  );
}

describe("ProductConfigForm - product list sidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "location", {
      writable: true,
      value: { reload: vi.fn() },
    });
  });

  it("S2: 渲染产品列表侧边栏，展示所有产品", async () => {
    vi.mocked(api.listProducts).mockResolvedValue([
      { id: "prod_a", name: "产品 A" },
      { id: "prod_b", name: "产品 B" },
    ]);
    vi.mocked(api.getProductConfig).mockResolvedValue(
      mockProductConfig({ id: "prod_a", default_name: "产品 A" })
    );
    vi.mocked(api.getProductConfigById).mockResolvedValue(
      mockProductConfig({ id: "prod_a", default_name: "产品 A" })
    );

    renderForm();

    await waitFor(() => {
      expect(screen.getByText("产品 A")).toBeInTheDocument();
    });
    expect(screen.getByText("产品 B")).toBeInTheDocument();
  });

  it("S2: 默认选中活跃产品，加载其配置", async () => {
    vi.mocked(api.listProducts).mockResolvedValue([
      { id: "prod_a", name: "产品 A" },
      { id: "prod_b", name: "产品 B" },
    ]);
    vi.mocked(api.getProductConfig).mockResolvedValue(
      mockProductConfig({ id: "prod_a", default_name: "产品 A" })
    );
    vi.mocked(api.getProductConfigById).mockResolvedValue(
      mockProductConfig({ id: "prod_a", default_name: "产品 A" })
    );

    renderForm();

    await waitFor(() => {
      // 表单中应显示活跃产品的配置
      const nameInput = screen.getByDisplayValue("产品 A") as HTMLInputElement;
      expect(nameInput).toBeInTheDocument();
    });
  });

  it("S4: 活跃产品与编辑产品视觉区分", async () => {
    vi.mocked(api.listProducts).mockResolvedValue([
      { id: "prod_a", name: "产品 A" },
      { id: "prod_b", name: "产品 B" },
    ]);
    vi.mocked(api.getProductConfig).mockResolvedValue(
      mockProductConfig({ id: "prod_a", default_name: "产品 A" })
    );
    vi.mocked(api.getProductConfigById).mockImplementation(async (id: string) => {
      if (id === "prod_a") return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
      return mockProductConfig({ id: "prod_b", default_name: "产品 B" });
    });

    renderForm();

    await waitFor(() => {
      expect(screen.getByText("产品 B")).toBeInTheDocument();
    });

    // 活跃产品应有特殊标记（active badge）
    const activeBadge = screen.getByText("当前活跃");
    expect(activeBadge).toBeInTheDocument();
  });
});

describe("ProductConfigForm - select and edit non-active product", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "location", {
      writable: true,
      value: { reload: vi.fn() },
    });
  });

  it("S3: 点击非活跃产品加载其配置", async () => {
    vi.mocked(api.listProducts).mockResolvedValue([
      { id: "prod_a", name: "产品 A" },
      { id: "prod_b", name: "产品 B" },
    ]);
    vi.mocked(api.getProductConfig).mockResolvedValue(
      mockProductConfig({ id: "prod_a", default_name: "产品 A" })
    );
    vi.mocked(api.getProductConfigById).mockImplementation(async (id: string) => {
      if (id === "prod_a") return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
      return mockProductConfig({ id: "prod_b", default_name: "产品 B", default_brand: "品牌 B" });
    });

    renderForm();

    await waitFor(() => {
      expect(screen.getByText("产品 B")).toBeInTheDocument();
    });

    // 点击产品 B
    fireEvent.click(screen.getByText("产品 B"));

    await waitFor(() => {
      expect(api.getProductConfigById).toHaveBeenCalledWith("prod_b");
    });

    // 表单应更新为产品 B 的配置
    await waitFor(() => {
      const brandInput = screen.getByDisplayValue("品牌 B") as HTMLInputElement;
      expect(brandInput).toBeInTheDocument();
    });
  });

  it("S5: 保存非活跃产品调用 saveProductConfigById 而非 saveProductConfig", async () => {
    vi.mocked(api.listProducts).mockResolvedValue([
      { id: "prod_a", name: "产品 A" },
      { id: "prod_b", name: "产品 B" },
    ]);
    vi.mocked(api.getProductConfig).mockResolvedValue(
      mockProductConfig({ id: "prod_a", default_name: "产品 A" })
    );
    vi.mocked(api.getProductConfigById).mockImplementation(async (id: string) => {
      if (id === "prod_a") return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
      return mockProductConfig({ id: "prod_b", default_name: "产品 B", default_brand: "品牌 B" });
    });
    vi.mocked(api.saveProductConfigById).mockResolvedValue(
      mockProductConfig({ id: "prod_b", default_name: "产品 B 已修改", default_brand: "品牌 B" })
    );

    renderForm();

    await waitFor(() => {
      expect(screen.getByText("产品 B")).toBeInTheDocument();
    });

    // 点击产品 B 切换到编辑它
    fireEvent.click(screen.getByText("产品 B"));

    await waitFor(() => {
      expect(api.getProductConfigById).toHaveBeenCalledWith("prod_b");
    });

    // 修改产品名
    const nameInput = await screen.findByDisplayValue("产品 B");
    fireEvent.change(nameInput, { target: { value: "产品 B 已修改" } });

    // 点击保存
    const saveBtn = screen.getByText("保存配置");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.saveProductConfigById).toHaveBeenCalledWith(
        "prod_b",
        expect.objectContaining({ default_name: "产品 B 已修改" })
      );
    });

    // 不应调用无参的 saveProductConfig
    expect(api.saveProductConfig).not.toHaveBeenCalled();
  });
});

describe("ProductConfigForm - empty state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("S6: 空产品列表显示稳定空状态及新建入口", async () => {
    vi.mocked(api.listProducts).mockResolvedValue([]);
    vi.mocked(api.getProductConfig).mockResolvedValue(
      mockProductConfig({ id: "", default_name: "", default_brand: "" })
    );

    renderForm();

    await waitFor(() => {
      expect(screen.getByText("暂无产品配置")).toBeInTheDocument();
    });
    expect(screen.getByText("新建产品")).toBeInTheDocument();
  });
});
