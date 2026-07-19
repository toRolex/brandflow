import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import ProductSelector from "../components/ProductSelector";
import { ProductProvider, useProducts } from "../ProductContext";
import type { ProductConfig } from "../types";

const mockConfig = (
	overrides: Partial<ProductConfig & { id?: string }> = {},
): ProductConfig & { id?: string } => ({
	id: "prod_a",
	default_name: "",
	default_brand: "",
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
		switchProduct: vi.fn(),
		createProduct: vi.fn(),
		renameProduct: vi.fn(),
		deleteProduct: vi.fn(),
	},
}));

function TestConsumer() {
	const { products, activeProductId, activeProductName, loading } =
		useProducts();
	return (
		<div>
			<div data-testid="loading">{loading ? "loading" : "ready"}</div>
			<div data-testid="active-id">{activeProductId}</div>
			<div data-testid="active-name">{activeProductName}</div>
			<div data-testid="product-count">{products.length}</div>
		</div>
	);
}

describe("ProductProvider", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("加载时拉取产品列表和活跃配置", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
			{ id: "prod_b", name: "产品 B" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockConfig({ default_name: "产品 A" }),
		);

		render(
			<ProductProvider>
				<TestConsumer />
			</ProductProvider>,
		);

		await waitFor(() => {
			expect(screen.getByTestId("active-id").textContent).toBe("prod_a");
		});
		expect(screen.getByTestId("active-name").textContent).toBe("产品 A");
		expect(screen.getByTestId("product-count").textContent).toBe("2");
	});

	it("无产品时显示空状态", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([]);
		vi.mocked(api.getProductConfig).mockResolvedValue(mockConfig({ id: "" }));

		render(
			<ProductProvider>
				<TestConsumer />
			</ProductProvider>,
		);

		await waitFor(() => {
			expect(screen.getByTestId("product-count").textContent).toBe("0");
		});
		expect(screen.getByTestId("active-id").textContent).toBe("");
	});

	it("switchProduct 调用 API 并刷新列表", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockConfig({ default_name: "产品 A" }),
		);
		vi.mocked(api.switchProduct).mockResolvedValue({
			active_product_id: "prod_b",
		});

		function Switcher() {
			const { switchProduct } = useProducts();
			return <button onClick={() => switchProduct("prod_b")}>切换</button>;
		}

		render(
			<ProductProvider>
				<Switcher />
			</ProductProvider>,
		);

		fireEvent.click(screen.getByText("切换"));

		await waitFor(() => {
			expect(api.switchProduct).toHaveBeenCalledWith("prod_b");
		});
		expect(api.listProducts).toHaveBeenCalledTimes(2);
	});

	it("createProduct 调用 API 并刷新列表", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockConfig({ default_name: "产品 A" }),
		);
		vi.mocked(api.createProduct).mockResolvedValue({
			id: "羊肚菌",
			name: "羊肚菌",
		});

		function Creator() {
			const { createProduct } = useProducts();
			return <button onClick={() => createProduct("羊肚菌")}>新建</button>;
		}

		render(
			<ProductProvider>
				<Creator />
			</ProductProvider>,
		);

		fireEvent.click(screen.getByText("新建"));

		await waitFor(() => {
			expect(api.createProduct).toHaveBeenCalledWith("羊肚菌");
		});
		expect(api.listProducts).toHaveBeenCalledTimes(2);
	});

	it("renameProduct 调用 API 并刷新列表", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockConfig({ default_name: "产品 A" }),
		);
		vi.mocked(api.renameProduct).mockResolvedValue({
			id: "prod_a",
			name: "新名称",
		});

		function Renamer() {
			const { renameProduct } = useProducts();
			return (
				<button onClick={() => renameProduct("prod_a", "新名称")}>
					重命名
				</button>
			);
		}

		render(
			<ProductProvider>
				<Renamer />
			</ProductProvider>,
		);

		fireEvent.click(screen.getByText("重命名"));

		await waitFor(() => {
			expect(api.renameProduct).toHaveBeenCalledWith("prod_a", "新名称");
		});
		expect(api.listProducts).toHaveBeenCalledTimes(2);
	});

	it("deleteProduct 调用 API 并刷新列表", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
			{ id: "prod_b", name: "产品 B" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockConfig({ default_name: "产品 A" }),
		);
		vi.mocked(api.deleteProduct).mockResolvedValue({
			status: "deleted",
			active_product_id: "prod_a",
		});

		function Deleter() {
			const { deleteProduct } = useProducts();
			return <button onClick={() => deleteProduct("prod_b")}>删除</button>;
		}

		render(
			<ProductProvider>
				<Deleter />
			</ProductProvider>,
		);

		fireEvent.click(screen.getByText("删除"));

		await waitFor(() => {
			expect(api.deleteProduct).toHaveBeenCalledWith("prod_b");
		});
		expect(api.listProducts).toHaveBeenCalledTimes(2);
	});
});

describe("ProductSelector", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		// 提供 window.location.reload 的 mock，避免测试时真刷新
		Object.defineProperty(window, "location", {
			writable: true,
			value: { reload: vi.fn() },
		});
	});

	it("初始未加载完成时显示占位文案", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockConfig({ default_name: "产品 A" }),
		);

		render(
			<ProductProvider>
				<ProductSelector />
			</ProductProvider>,
		);

		// 在 Provider 完成首次加载前，products 为空
		expect(screen.getByText("暂未配置产品")).toBeInTheDocument();

		await waitFor(() => {
			expect(screen.getByText("产品 A")).toBeInTheDocument();
		});
	});

	it("有产品时渲染下拉按钮", () => {
		vi.mocked(api.listProducts).mockResolvedValue([
			{ id: "prod_a", name: "产品 A" },
		]);
		vi.mocked(api.getProductConfig).mockResolvedValue(
			mockConfig({ default_name: "产品 A" }),
		);

		render(
			<ProductProvider>
				<ProductSelector />
			</ProductProvider>,
		);

		return waitFor(() => {
			expect(screen.getByText("产品 A")).toBeInTheDocument();
		});
	});

	it("无产品时显示占位文案", async () => {
		vi.mocked(api.listProducts).mockResolvedValue([]);
		vi.mocked(api.getProductConfig).mockResolvedValue(mockConfig());

		render(
			<ProductProvider>
				<ProductSelector />
			</ProductProvider>,
		);

		await waitFor(() => {
			expect(screen.getByText("暂未配置产品")).toBeInTheDocument();
		});
	});
});
