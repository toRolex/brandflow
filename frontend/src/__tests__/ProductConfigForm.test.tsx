import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { ProductProvider } from "../ProductContext";
import ProductConfigForm from "../pages/ProductConfigForm";
import type { ProductConfig } from "../types";

const mockProductConfig = (
	overrides: Partial<ProductConfig & { id?: string; name?: string }> = {},
): ProductConfig & { id?: string; name?: string } => ({
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
		createProduct: vi.fn(),
		renameProduct: vi.fn(),
		deleteProduct: vi.fn(),
	},
}));

function renderForm() {
	return render(
		<ProductProvider>
			<ProductConfigForm />
		</ProductProvider>,
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
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockResolvedValue(
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
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
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockResolvedValue(
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);

		renderForm();

		await waitFor(() => {
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
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockImplementation(
			async (id: string) => {
				if (id === "prod_a")
					return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
				return mockProductConfig({ id: "prod_b", default_name: "产品 B" });
			},
		);

		renderForm();

		await waitFor(() => {
			expect(screen.getByText("产品 B")).toBeInTheDocument();
		});

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
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockImplementation(
			async (id: string) => {
				if (id === "prod_a")
					return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
				return mockProductConfig({
					id: "prod_b",
					default_name: "产品 B",
					default_brand: "品牌 B",
				});
			},
		);

		renderForm();

		await waitFor(() => {
			expect(screen.getByText("产品 B")).toBeInTheDocument();
		});

		fireEvent.click(screen.getByText("产品 B"));

		await waitFor(() => {
			expect(api.getProductConfigById).toHaveBeenCalledWith("prod_b");
		});

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
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockImplementation(
			async (id: string) => {
				if (id === "prod_a")
					return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
				return mockProductConfig({
					id: "prod_b",
					default_name: "产品 B",
					default_brand: "品牌 B",
				});
			},
		);
		vi.mocked(api.saveProductConfigById).mockResolvedValue(
			mockProductConfig({
				id: "prod_b",
				default_name: "产品 B 已修改",
				default_brand: "品牌 B",
			}),
		);

		renderForm();

		await waitFor(() => {
			expect(screen.getByText("产品 B")).toBeInTheDocument();
		});

		fireEvent.click(screen.getByText("产品 B"));

		await waitFor(() => {
			expect(api.getProductConfigById).toHaveBeenCalledWith("prod_b");
		});

		const nameInput = await screen.findByDisplayValue("产品 B");
		fireEvent.change(nameInput, { target: { value: "产品 B 已修改" } });

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(api.saveProductConfigById).toHaveBeenCalledWith(
				"prod_b",
				expect.objectContaining({ default_name: "产品 B 已修改" }),
			);
		});

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
			mockProductConfig({ id: "", default_name: "", default_brand: "" }),
		);

		renderForm();

		await waitFor(() => {
			expect(screen.getByText("暂无产品配置")).toBeInTheDocument();
		});
		expect(screen.getByText("新建产品")).toBeInTheDocument();
	});
});

describe("ProductConfigForm - create product", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		Object.defineProperty(window, "location", {
			writable: true,
			value: { reload: vi.fn() },
		});
	});

	it("新建产品调用 createProduct API", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockResolvedValue(
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.createProduct).mockResolvedValue({
			id: "羊肚菌",
			name: "羊肚菌",
		});

		renderForm();

		await waitFor(() => {
			expect(screen.getByText("产品 A")).toBeInTheDocument();
		});

		// Click "+ 新建产品"
		fireEvent.click(screen.getByText("+ 新建产品"));

		// Type product name
		const nameInput = screen.getByPlaceholderText("输入产品名称，如：示例产品");
		fireEvent.change(nameInput, { target: { value: "羊肚菌" } });

		// Click "创建并编辑"
		fireEvent.click(screen.getByText("创建并编辑"));

		await waitFor(() => {
			expect(api.createProduct).toHaveBeenCalledWith("羊肚菌");
		});
	});
});

describe("ProductConfigForm - rename product", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		Object.defineProperty(window, "location", {
			writable: true,
			value: { reload: vi.fn() },
		});
	});

	it("重命名产品调用 renameProduct API", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
			{ id: "prod_b", name: "产品 B" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockImplementation(
			async (id: string) => {
				if (id === "prod_a")
					return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
				return mockProductConfig({
					id: "prod_b",
					default_name: "产品 B",
					default_brand: "品牌 B",
				});
			},
		);
		vi.mocked(api.renameProduct).mockResolvedValue({
			id: "prod_b",
			name: "产品 B 重命名",
		});

		renderForm();

		await waitFor(() => {
			expect(screen.getByText("产品 B")).toBeInTheDocument();
		});

		// Find and click rename button for prod_b (the non-active product)
		const renameButtons = screen.getAllByTitle("重命名");
		// prod_b is the second product (index 1), the non-active one
		const renameBtn = renameButtons[1];
		fireEvent.click(renameBtn);

		// Type new name and confirm
		await waitFor(() => {
			const input = screen.getByDisplayValue("产品 B") as HTMLInputElement;
			fireEvent.change(input, { target: { value: "产品 B 重命名" } });
		});

		// Click confirm (checkmark)
		const confirmBtn = screen.getByTitle("确认");
		fireEvent.click(confirmBtn);

		await waitFor(() => {
			expect(api.renameProduct).toHaveBeenCalledWith("prod_b", "产品 B 重命名");
		});
	});
});

describe("ProductConfigForm - delete product", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		Object.defineProperty(window, "location", {
			writable: true,
			value: { reload: vi.fn() },
		});
	});

	it("删除产品前显示确认对话框", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
			{ id: "prod_b", name: "产品 B" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockImplementation(
			async (id: string) => {
				if (id === "prod_a")
					return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
				return mockProductConfig({
					id: "prod_b",
					default_name: "产品 B",
					default_brand: "品牌 B",
				});
			},
		);

		renderForm();

		await waitFor(() => {
			expect(screen.getByText("产品 B")).toBeInTheDocument();
		});

		// Click delete button for prod_b (non-active product)
		const deleteButtons = screen.getAllByTitle("删除");
		fireEvent.click(deleteButtons[0]);

		await waitFor(() => {
			expect(screen.getByText("确认删除产品")).toBeInTheDocument();
		});
	});

	it("确认删除后调用 deleteProduct API", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
			{ id: "prod_b", name: "产品 B" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockImplementation(
			async (id: string) => {
				if (id === "prod_a")
					return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
				return mockProductConfig({
					id: "prod_b",
					default_name: "产品 B",
					default_brand: "品牌 B",
				});
			},
		);
		vi.mocked(api.deleteProduct).mockResolvedValue({
			status: "deleted",
			active_product_id: "prod_a",
		});

		renderForm();

		await waitFor(() => {
			expect(screen.getByText("产品 B")).toBeInTheDocument();
		});

		// Click delete button
		const deleteButtons = screen.getAllByTitle("删除");
		fireEvent.click(deleteButtons[0]);

		await waitFor(() => {
			expect(screen.getByText("确认删除产品")).toBeInTheDocument();
		});

		// Click confirm
		fireEvent.click(screen.getByText("确认删除"));

		await waitFor(() => {
			expect(api.deleteProduct).toHaveBeenCalledWith("prod_b");
		});
	});

	it("取消删除不调用 API", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
			{ id: "prod_b", name: "产品 B" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockProductConfig({ id: "prod_a", default_name: "产品 A" }),
		);
		vi.mocked(api.getProductConfigById).mockImplementation(
			async (id: string) => {
				if (id === "prod_a")
					return mockProductConfig({ id: "prod_a", default_name: "产品 A" });
				return mockProductConfig({
					id: "prod_b",
					default_name: "产品 B",
					default_brand: "品牌 B",
				});
			},
		);

		renderForm();

		await waitFor(() => {
			expect(screen.getByText("产品 B")).toBeInTheDocument();
		});

		const deleteButtons = screen.getAllByTitle("删除");
		fireEvent.click(deleteButtons[0]);

		await waitFor(() => {
			expect(screen.getByText("确认删除产品")).toBeInTheDocument();
		});

		// Click cancel
		fireEvent.click(screen.getByText("取消"));

		await waitFor(() => {
			expect(screen.queryByText("确认删除产品")).not.toBeInTheDocument();
		});

		expect(api.deleteProduct).not.toHaveBeenCalled();
	});
});
