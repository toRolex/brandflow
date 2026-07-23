import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import ProjectWorkbench from "../ProjectWorkbench";

vi.mock("../../api/client", () => ({
	api: {
		getProject: vi.fn(),
		listMusic: vi.fn(),
		listTemplates: vi.fn(),
		createJob: vi.fn(),
		batchCreateJobs: vi.fn(),
		uploadJobAudio: vi.fn(),
		enqueueJob: vi.fn(),
	},
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
	const actual = await vi.importActual("react-router-dom");
	return {
		...(actual as object),
		useNavigate: () => mockNavigate,
	};
});

const MOCK_PROJECT = {
	id: "p1",
	name: "测试项目",
	status: "active",
	job_count: 2,
	jobs: [
		{
			job_id: "job-1",
			product: "产品A",
			phase: "completed" as const,
			review_status: "approved" as const,
			phase_index: 14,
			phase_total: 14,
		},
		{
			job_id: "job-2",
			product: "产品B",
			phase: "asset_review" as const,
			review_status: "pending" as const,
			phase_index: 2,
			phase_total: 14,
			asset_review_unresolved_count: 3,
		},
	],
};

function renderPage() {
	return render(
		<MemoryRouter initialEntries={["/projects/p1"]}>
			<Routes>
				<Route path="/projects/:id" element={<ProjectWorkbench />} />
			</Routes>
		</MemoryRouter>,
	);
}

describe("ProjectWorkbench create job modal (#272)", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getProject).mockResolvedValue(MOCK_PROJECT);
		vi.mocked(api.listMusic).mockResolvedValue({ tracks: [] });
		vi.mocked(api.listTemplates).mockResolvedValue([]);
	});

	describe("default view", () => {
		it("shows jobs list and hides create form by default", async () => {
			renderPage();

			await waitFor(() => {
				expect(screen.getByText("job-1")).toBeInTheDocument();
			});
			expect(screen.getByText("待处理素材：3 条")).toBeInTheDocument();

			expect(screen.getByText("job-2")).toBeInTheDocument();
			expect(screen.queryByText("创建新 Job")).not.toBeInTheDocument();
			expect(
				screen.queryByPlaceholderText("如：龙井茶"),
			).not.toBeInTheDocument();
		});

		it("renders header create button", async () => {
			renderPage();

			await waitFor(() => {
				expect(screen.getByText("job-1")).toBeInTheDocument();
			});

			expect(
				screen.getByRole("button", { name: "＋ 新建 Job" }),
			).toBeInTheDocument();
		});
	});

	describe("modal gating", () => {
		it("opens create modal when header button is clicked", async () => {
			renderPage();

			await waitFor(() => {
				expect(screen.getByText("job-1")).toBeInTheDocument();
			});

			fireEvent.click(screen.getByRole("button", { name: "＋ 新建 Job" }));

			expect(screen.getByText("创建新 Job")).toBeInTheDocument();
			expect(screen.getByPlaceholderText("默认使用产品名")).toBeInTheDocument();
		});

		it("allows switching between single and batch creation inside modal", async () => {
			renderPage();

			await waitFor(() => {
				expect(screen.getByText("job-1")).toBeInTheDocument();
			});

			fireEvent.click(screen.getByRole("button", { name: "＋ 新建 Job" }));

			expect(screen.getByPlaceholderText("默认使用产品名")).toBeInTheDocument();
			expect(screen.queryByLabelText("创建数量")).not.toBeInTheDocument();

			fireEvent.click(screen.getByLabelText("批量创建"));
			expect(screen.getByLabelText("创建数量")).toBeInTheDocument();

			fireEvent.click(screen.getByLabelText("单个创建"));
			expect(screen.getByPlaceholderText("默认使用产品名")).toBeInTheDocument();
			expect(screen.queryByLabelText("创建数量")).not.toBeInTheDocument();
		});
	});

	describe("single job creation", () => {
		it("closes modal, stays on list, and refreshes after success", async () => {
			vi.mocked(api.createJob).mockResolvedValue({
				job_id: "job-new",
				project_id: "p1",
				product: "新产品",
				platforms: ["douyin"],
				phase: "queued" as const,
				review_status: "none" as const,
				execution: {
					status: "pending" as const,
					current_attempt: 0,
					max_attempts: 3,
					error: null,
				},
				artifacts: [],
			});
			vi.mocked(api.getProject)
				.mockResolvedValueOnce(MOCK_PROJECT)
				.mockResolvedValueOnce({
					...MOCK_PROJECT,
					jobs: [
						...MOCK_PROJECT.jobs,
						{
							job_id: "job-new",
							product: "新产品",
							phase: "queued" as const,
							review_status: "none" as const,
							phase_index: 1,
							phase_total: 14,
						},
					],
				});

			renderPage();

			await waitFor(() => {
				expect(screen.getByText("job-1")).toBeInTheDocument();
			});

			fireEvent.click(screen.getByRole("button", { name: "＋ 新建 Job" }));

			fireEvent.click(screen.getByText("创建并开始生产"));

			await waitFor(() => {
				expect(api.createJob).toHaveBeenCalledWith(
					"p1",
					expect.objectContaining({ platforms: ["douyin", "xiaohongshu"] }),
				);
			});

			// Modal should close and list should refresh
			await waitFor(() => {
				expect(screen.queryByText("创建新 Job")).not.toBeInTheDocument();
			});
			await waitFor(() => {
				expect(screen.getByText("job-new")).toBeInTheDocument();
			});

			expect(mockNavigate).not.toHaveBeenCalled();
			expect(api.getProject).toHaveBeenCalledTimes(2);
		});
	});

	describe("batch job creation", () => {
		it("calls batchCreateJobs and refreshes without navigating", async () => {
			vi.mocked(api.batchCreateJobs).mockResolvedValue({
				product: "批量产品",
				platforms: ["douyin"],
				review_strategy: "review_each",
				count: 2,
				results: [
					{
						job_id: "batch-1",
						display_index: "001",
						product: "批量产品",
						name: "批量产品 #001",
						phase: "queued" as const,
						skip_subtitle: false,
						mode: "generate",
						review_strategy: "review_each",
					},
					{
						job_id: "batch-2",
						display_index: "002",
						product: "批量产品",
						name: "批量产品 #002",
						phase: "queued" as const,
						skip_subtitle: false,
						mode: "generate",
						review_strategy: "review_each",
					},
				],
			});
			vi.mocked(api.getProject)
				.mockResolvedValueOnce(MOCK_PROJECT)
				.mockResolvedValueOnce({
					...MOCK_PROJECT,
					jobs: [
						...MOCK_PROJECT.jobs,
						{
							job_id: "batch-1",
							product: "批量产品",
							phase: "queued" as const,
							review_status: "none" as const,
							phase_index: 1,
							phase_total: 14,
						},
						{
							job_id: "batch-2",
							product: "批量产品",
							phase: "queued" as const,
							review_status: "none" as const,
							phase_index: 1,
							phase_total: 14,
						},
					],
				});

			renderPage();

			await waitFor(() => {
				expect(screen.getByText("job-1")).toBeInTheDocument();
			});

			fireEvent.click(screen.getByRole("button", { name: "＋ 新建 Job" }));

			fireEvent.click(screen.getByLabelText("批量创建"));

			fireEvent.click(screen.getByRole("button", { name: /批量创建/ }));

			await waitFor(() => {
				expect(api.batchCreateJobs).toHaveBeenCalledWith(
					"p1",
					expect.objectContaining({ review_strategy: "review_each" }),
				);
			});

			await waitFor(() => {
				expect(screen.getByText("batch-1")).toBeInTheDocument();
			});
			expect(screen.getByText("batch-2")).toBeInTheDocument();

			expect(mockNavigate).not.toHaveBeenCalled();
			expect(api.getProject).toHaveBeenCalledTimes(2);
		});
	});
});
