import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import ProjectList from "../ProjectList";

vi.mock("../../api/client", () => ({
	api: {
		listProjects: vi.fn(),
		createProject: vi.fn(),
		deleteProject: vi.fn(),
	},
}));

const mockProjects = [
	{ id: "p1", name: "项目 A", status: "active", job_count: 2 },
	{ id: "p2", name: "项目 B", status: "draft", job_count: 0 },
	{ id: "p3", name: "项目 C", status: "active", job_count: 5 },
];

function renderList() {
	return render(
		<MemoryRouter>
			<ProjectList />
		</MemoryRouter>,
	);
}

async function waitForLoading() {
	await waitFor(() => {
		expect(screen.queryByText("加载中...")).not.toBeInTheDocument();
	});
}

describe("ProjectList", () => {
	beforeEach(() => {
		vi.resetAllMocks();
		vi.mocked(api.listProjects).mockResolvedValue(mockProjects);
	});

	it("renders project list", async () => {
		renderList();
		await waitForLoading();
		expect(screen.getByText("项目 A")).toBeInTheDocument();
		expect(screen.getByText("项目 B")).toBeInTheDocument();
		expect(screen.getByText("项目 C")).toBeInTheDocument();
	});

	it("toggles selection via row checkbox", async () => {
		renderList();
		await waitForLoading();

		const checkboxA = screen.getByLabelText("选择项目 项目 A");
		fireEvent.click(checkboxA);
		expect(screen.getByText("已选 1 项")).toBeInTheDocument();

		fireEvent.click(checkboxA);
		expect(screen.queryByText("已选 1 项")).not.toBeInTheDocument();
	});

	it("selects and clears all via header checkbox", async () => {
		renderList();
		await waitForLoading();

		const headerCheckbox = screen.getByLabelText("全选");
		fireEvent.click(headerCheckbox);
		expect(screen.getByText("已选 3 项")).toBeInTheDocument();
		expect(screen.getByLabelText("选择项目 项目 A")).toBeChecked();
		expect(screen.getByLabelText("选择项目 项目 C")).toBeChecked();

		fireEvent.click(headerCheckbox);
		expect(screen.queryByText("已选 3 项")).not.toBeInTheDocument();
		expect(screen.getByLabelText("选择项目 项目 A")).not.toBeChecked();
	});

	it("sets header checkbox to indeterminate when partially selected", async () => {
		renderList();
		await waitForLoading();

		const headerCheckbox = screen.getByLabelText(
			"全选",
		) as HTMLInputElement;
		fireEvent.click(screen.getByLabelText("选择项目 项目 A"));

		await waitFor(() => {
			expect(headerCheckbox.indeterminate).toBe(true);
		});
		expect(headerCheckbox.checked).toBe(false);
	});

	it("bulk deletes selected projects after confirm", async () => {
		vi.mocked(api.deleteProject).mockResolvedValue({ ok: true });

		renderList();
		await waitForLoading();

		fireEvent.click(screen.getByLabelText("全选"));
		fireEvent.click(screen.getByText("批量删除"));

		expect(
			screen.getByText("确定要删除已选中的 3 个项目吗？此操作不可撤销。"),
		).toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

		await waitFor(() => {
			expect(api.deleteProject).toHaveBeenCalledTimes(3);
		});
		expect(api.deleteProject).toHaveBeenCalledWith("p1");
		expect(api.deleteProject).toHaveBeenCalledWith("p2");
		expect(api.deleteProject).toHaveBeenCalledWith("p3");
		expect(screen.getByText("已删除 3 个项目")).toBeInTheDocument();
	});

	it("shows partial failure summary", async () => {
		vi.mocked(api.deleteProject)
			.mockResolvedValueOnce({ ok: true })
			.mockRejectedValueOnce(new Error("boom"));

		renderList();
		await waitForLoading();

		fireEvent.click(screen.getByLabelText("选择项目 项目 A"));
		fireEvent.click(screen.getByLabelText("选择项目 项目 B"));
		fireEvent.click(screen.getByText("批量删除"));
		fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

		await waitFor(() => {
			expect(screen.getByText("1 成功，1 失败")).toBeInTheDocument();
		});
	});

	it("removes single-deleted project from selection", async () => {
		vi.mocked(api.deleteProject).mockResolvedValue({ ok: true });

		renderList();
		await waitForLoading();

		fireEvent.click(screen.getByLabelText("选择项目 项目 A"));
		fireEvent.click(screen.getByLabelText("选择项目 项目 B"));
		expect(screen.getByText("已选 2 项")).toBeInTheDocument();

		fireEvent.click(screen.getAllByText("删除")[0]);
		fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

		await waitFor(() => {
			expect(api.deleteProject).toHaveBeenCalledWith("p1");
		});
		expect(screen.getByText("已选 1 项")).toBeInTheDocument();
	});

	it("shows error when creating project with duplicate name", async () => {
		renderList();
		await waitForLoading();

		const input = screen.getByPlaceholderText("新项目名称");
		fireEvent.change(input, { target: { value: "项目 A" } });
		fireEvent.click(screen.getByText("创建项目"));

		await waitFor(() => {
			expect(
				screen.getByText("项目名称已存在，请使用其他名称"),
			).toBeInTheDocument();
		});
	});
});
