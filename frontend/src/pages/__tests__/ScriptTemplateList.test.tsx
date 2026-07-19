import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import ScriptTemplateList from "../ScriptTemplateList";

vi.mock("../../api/client", () => ({
	api: {
		listTemplates: vi.fn(),
		deleteTemplate: vi.fn(),
	},
}));

const MOCK_TEMPLATES = [
	{
		id: "tmpl_001",
		name: "通用带货脚本",
		description: "适用于产品类短视频展示",
		slots: [
			{
				type: "hook" as const,
				label: "开头钩子",
				required: true,
				max_length: 60,
				hint: "",
			},
		],
		variables: [
			{
				name: "product_name",
				label: "产品名",
				source: "product_config" as const,
			},
		],
		default_config_override: {},
	},
	{
		id: "tmpl_002",
		name: "产品测评脚本",
		description: "产品测评类短视频",
		slots: [
			{
				type: "hook" as const,
				label: "开场白",
				required: true,
				max_length: 60,
				hint: "",
			},
			{
				type: "selling_point" as const,
				label: "测评点",
				required: true,
				max_length: 200,
				hint: "",
			},
		],
		variables: [],
		default_config_override: {},
	},
];

function renderPage() {
	return render(
		<BrowserRouter>
			<ScriptTemplateList />
		</BrowserRouter>,
	);
}

describe("ScriptTemplateList", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.listTemplates).mockResolvedValue(MOCK_TEMPLATES);
	});

	it("加载时调用 listTemplates API", async () => {
		renderPage();
		expect(api.listTemplates).toHaveBeenCalledTimes(1);
	});

	it("显示模板列表", async () => {
		renderPage();
		await waitFor(() => {
			expect(screen.getByText("通用带货脚本")).toBeInTheDocument();
		});
		expect(screen.getByText("产品测评脚本")).toBeInTheDocument();
	});

	it("显示模板描述和 slot 数量", async () => {
		renderPage();
		await waitFor(() => {
			expect(screen.getByText("适用于产品类短视频展示")).toBeInTheDocument();
		});
		expect(screen.getByText("1 个片段")).toBeInTheDocument();
		expect(screen.getByText(/产品测评脚本/)).toBeInTheDocument();
		expect(screen.getByText("2 个片段")).toBeInTheDocument();
	});

	it("加载失败时显示错误", async () => {
		vi.mocked(api.listTemplates).mockRejectedValue(new Error("Network Error"));
		renderPage();
		await waitFor(() => {
			expect(screen.getByText("加载模板列表失败")).toBeInTheDocument();
		});
	});

	it("空列表显示空状态", async () => {
		vi.mocked(api.listTemplates).mockResolvedValue([]);
		renderPage();
		await waitFor(() => {
			expect(screen.getByText("暂无脚本模板")).toBeInTheDocument();
		});
	});

	it("删除按钮调用 deleteTemplate API", async () => {
		vi.mocked(api.deleteTemplate).mockResolvedValue({ status: "ok" });
		renderPage();
		await waitFor(() => {
			expect(screen.getByText("通用带货脚本")).toBeInTheDocument();
		});

		const deleteButtons = screen.getAllByText("删除");
		fireEvent.click(deleteButtons[0]);

		await waitFor(() => {
			expect(api.deleteTemplate).toHaveBeenCalledWith("tmpl_001");
		});
	});

	it("删除后刷新列表", async () => {
		vi.mocked(api.deleteTemplate).mockResolvedValue({ status: "ok" });
		renderPage();
		await waitFor(() => {
			expect(screen.getByText("通用带货脚本")).toBeInTheDocument();
		});

		const deleteButtons = screen.getAllByText("删除");
		fireEvent.click(deleteButtons[0]);

		await waitFor(() => {
			expect(api.listTemplates).toHaveBeenCalledTimes(2);
		});
	});

	it("新建按钮链接到编辑器", async () => {
		renderPage();
		await waitFor(() => {
			expect(screen.getByText("新建模板")).toBeInTheDocument();
		});
		const newBtn = screen.getByText("新建模板");
		expect(newBtn.closest("a")).toHaveAttribute(
			"href",
			"/system/config/templates/new",
		);
	});
});
