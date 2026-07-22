import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import ProductConfigForm from "../ProductConfigForm";

vi.mock("../../api/client", () => ({
	api: {
		getProductConfig: vi.fn(),
		saveProductConfig: vi.fn(),
		resetProductConfig: vi.fn(),
		listProducts: vi.fn(),
		switchProduct: vi.fn(),
	},
}));

let mockUseProducts: ReturnType<
	typeof import("../../ProductContext").useProducts
>;

vi.mock("../../ProductContext", () => ({
	useProducts: () => mockUseProducts,
	ProductProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const MOCK_CONFIG = {
	default_name: "示例产品",
	default_brand: "示例品牌",
	script: {
		scene: "产品展示、制作过程、成品呈现",
		material: "产品近景、细节处理、使用场景",
		system_prompt: "你是一位美食短视频文案专家。",
	},
};

function defaultMockProducts() {
	return {
		products: [{ id: "test", name: "Test Product" }],
		activeProductId: "test",
		activeProductName: "Test Product",
		activeProductConfig: null,
		loading: false,
		switchProduct: vi.fn(),
		refreshProducts: vi.fn(),
		createProduct: vi.fn(),
		renameProduct: vi.fn(),
		deleteProduct: vi.fn(),
	};
}

describe("ProductConfigForm", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getProductConfig).mockResolvedValue(MOCK_CONFIG);
		mockUseProducts = defaultMockProducts();
	});

	it("加载时调用 API 并回显配置", async () => {
		render(<ProductConfigForm />);
		expect(api.getProductConfig).toHaveBeenCalledTimes(1);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});
		expect(screen.getByDisplayValue("示例品牌")).toBeInTheDocument();
		expect(
			screen.getByDisplayValue("产品展示、制作过程、成品呈现"),
		).toBeInTheDocument();
		expect(
			screen.getByDisplayValue("产品近景、细节处理、使用场景"),
		).toBeInTheDocument();
		expect(
			screen.getByDisplayValue("你是一位美食短视频文案专家。"),
		).toBeInTheDocument();
	});

	it("加载失败时显示错误提示", async () => {
		vi.mocked(api.getProductConfig).mockRejectedValue(
			new Error("Network Error"),
		);
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByText("加载产品配置失败")).toBeInTheDocument();
		});
	});

	it("保存按钮调用 PUT API", async () => {
		vi.mocked(api.saveProductConfig).mockResolvedValue(MOCK_CONFIG);
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
			expect(api.saveProductConfig).toHaveBeenCalledWith(
				expect.objectContaining({
					default_name: "示例产品",
					default_brand: "示例品牌",
				}),
			);
		});
	});

	it("保存成功后显示成功提示", async () => {
		vi.mocked(api.saveProductConfig).mockResolvedValue(MOCK_CONFIG);
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(screen.getByText("配置已保存")).toBeInTheDocument();
		});
	});

	it("保存失败时显示错误提示", async () => {
		vi.mocked(api.saveProductConfig).mockRejectedValue(
			new Error("Save failed"),
		);
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(screen.getByText("保存失败")).toBeInTheDocument();
		});
	});

	it("重置按钮调用 DELETE API", async () => {
		vi.mocked(api.resetProductConfig).mockResolvedValue({ status: "ok" });
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const resetBtn = screen.getByText("重置为默认值");
		fireEvent.click(resetBtn);

		await waitFor(() => {
			expect(api.resetProductConfig).toHaveBeenCalledTimes(1);
		});
	});

	it("重置后重新加载配置", async () => {
		const defaultConfig = {
			default_name: "",
			default_brand: "",
			script: {
				scene: "默认场景描述",
				material: "默认素材描述",
				system_prompt: "默认系统提示词",
			},
		};
		vi.mocked(api.resetProductConfig).mockResolvedValue({ status: "ok" });
		// First call returns MOCK_CONFIG, reload after reset returns default
		vi.mocked(api.getProductConfig).mockReset();
		vi.mocked(api.getProductConfig).mockResolvedValueOnce(MOCK_CONFIG);
		vi.mocked(api.getProductConfig).mockResolvedValueOnce(defaultConfig);

		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const resetBtn = screen.getByText("重置为默认值");
		fireEvent.click(resetBtn);

		await waitFor(() => {
			expect(api.getProductConfig).toHaveBeenCalledTimes(2);
		});
	});

	it("修改字段值后输入框反映新值", async () => {
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const nameInput = screen.getByDisplayValue("示例产品");
		fireEvent.change(nameInput, { target: { value: "新产品名称" } });

		expect(screen.getByDisplayValue("新产品名称")).toBeInTheDocument();
	});

	it("表单验证：产品名为空时显示错误", async () => {
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const nameInput = screen.getByDisplayValue("示例产品");
		fireEvent.change(nameInput, { target: { value: "" } });

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(screen.getByText("产品名不能为空")).toBeInTheDocument();
		});

		// API should NOT be called when validation fails
		expect(api.saveProductConfig).not.toHaveBeenCalled();
	});

	it("表单验证：品牌名为空时显示错误", async () => {
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const brandInput = screen.getByDisplayValue("示例品牌");
		fireEvent.change(brandInput, { target: { value: "" } });

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(screen.getByText("品牌名不能为空")).toBeInTheDocument();
		});

		expect(api.saveProductConfig).not.toHaveBeenCalled();
	});

	it("表单验证：产品名字数超过限制时显示错误", async () => {
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const nameInput = screen.getByDisplayValue("示例产品");
		fireEvent.change(nameInput, { target: { value: "a".repeat(51) } });

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(screen.getByText("产品名不能超过50字")).toBeInTheDocument();
		});

		expect(api.saveProductConfig).not.toHaveBeenCalled();
	});

	it("表单验证：品牌名字数超过限制时显示错误", async () => {
		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const brandInput = screen.getByDisplayValue("示例品牌");
		fireEvent.change(brandInput, { target: { value: "a".repeat(51) } });

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(screen.getByText("品牌名不能超过50字")).toBeInTheDocument();
		});

		expect(api.saveProductConfig).not.toHaveBeenCalled();
	});

	it("保存时显示保存中状态", async () => {
		// Return a promise that never resolves during the test
		vi.mocked(api.saveProductConfig).mockImplementation(
			() =>
				new Promise((resolve) => setTimeout(() => resolve(MOCK_CONFIG), 1000)),
		);

		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(screen.getByText("保存中...")).toBeInTheDocument();
		});
	});

	it("页面标题正确显示", async () => {
		render(<ProductConfigForm />);
		await waitFor(() => {
			expect(screen.getByText("产品配置")).toBeInTheDocument();
		});
	});

	it("创建产品后自动切换到新产品编辑状态", async () => {
		// Mock createProduct to simulate #208: new product becomes active
		mockUseProducts.createProduct = vi.fn(async (name: string) => {
			mockUseProducts = {
				...mockUseProducts,
				products: [...mockUseProducts.products, { id: "test2", name }],
				activeProductId: "test2",
				activeProductName: name,
			};
		});

		const newConfig = {
			default_name: "新产品",
			default_brand: "新品牌",
			script: { scene: "", material: "", system_prompt: "" },
		};
		vi.mocked(api.getProductConfig)
			.mockReset()
			.mockResolvedValueOnce(MOCK_CONFIG)
			.mockResolvedValueOnce(newConfig);

		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		// Click "+ 新建产品" in sidebar
		fireEvent.click(screen.getByText("+ 新建产品"));

		await waitFor(() => {
			expect(
				screen.getByPlaceholderText("输入产品名称，如：示例产品"),
			).toBeInTheDocument();
		});

		// Enter product name
		fireEvent.change(
			screen.getByPlaceholderText("输入产品名称，如：示例产品"),
			{ target: { value: "新产品" } },
		);

		// Click "创建并编辑"
		fireEvent.click(screen.getByText("创建并编辑"));

		// Should call getProductConfig twice (initial + after create)
		await waitFor(() => {
			expect(api.getProductConfig).toHaveBeenCalledTimes(2);
		});

		// Form should show new product's config
		await waitFor(() => {
			expect(screen.getByDisplayValue("新产品")).toBeInTheDocument();
		});
	});

	it("重置后产品保留在列表中", async () => {
		vi.mocked(api.resetProductConfig).mockResolvedValue({ status: "ok" });
		const defaultConfig = {
			default_name: "",
			default_brand: "",
			script: {
				scene: "默认场景描述",
				material: "默认素材描述",
				system_prompt: "默认系统提示词",
			},
		};
		vi.mocked(api.getProductConfig).mockReset();
		vi.mocked(api.getProductConfig).mockResolvedValueOnce(MOCK_CONFIG);
		vi.mocked(api.getProductConfig).mockResolvedValueOnce(defaultConfig);

		render(<ProductConfigForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("示例产品")).toBeInTheDocument();
		});

		// Product should be in the sidebar
		expect(screen.getByText("Test Product")).toBeInTheDocument();

		const resetBtn = screen.getByText("重置为默认值");
		fireEvent.click(resetBtn);

		// After reset, form shows default config
		await waitFor(() => {
			expect(api.getProductConfig).toHaveBeenCalledTimes(2);
		});

		// Product still visible in sidebar
		expect(screen.getByText("Test Product")).toBeInTheDocument();
	});
});
