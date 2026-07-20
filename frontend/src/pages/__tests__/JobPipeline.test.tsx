import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import JobPipeline from "../JobPipeline";

vi.mock("../../api/client", () => ({
	api: {
		getJob: vi.fn(),
		retryJob: vi.fn(),
		pauseJob: vi.fn(),
		getJobLogs: vi.fn(),
		migrateScenes: vi.fn(),
		getSceneFolders: vi.fn(),
		getTTSVoices: vi.fn(),
		getJobTTSVoice: vi.fn(),
		updateJobTTSVoice: vi.fn(),
		previewJobTTS: vi.fn(),
		approveReview: vi.fn(),
		rejectReview: vi.fn(),
		createExport: vi.fn(),
		getExportStatus: vi.fn(),
		downloadExport: vi.fn(),
	},
}));

vi.mock("../../components/PipelineSidebar", () => ({
	default: () => <aside />,
}));

const failedJob = {
	job_id: "job-170",
	project_id: "project-1",
	product: "product",
	platforms: ["douyin"],
	phase: "failed" as const,
	failed_phase: "video_rendering" as const,
	review_status: "none" as const,
	artifacts: [],
	execution: {
		status: "failed" as const,
		current_attempt: 3,
		max_attempts: 3,
		error: {
			code: "VIDEO_SOURCE_MISSING",
			message: "No usable video source is available.",
			retryable: false as const,
		},
	},
};

function renderPage() {
	return render(
		<MemoryRouter initialEntries={["/jobs/job-170"]}>
			<Routes>
				<Route path="/jobs/:id" element={<JobPipeline />} />
			</Routes>
		</MemoryRouter>,
	);
}

describe("JobPipeline execution failure workflow", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getJob).mockResolvedValue(failedJob);
		vi.mocked(api.retryJob).mockResolvedValue({
			status: "phase_queued_for_retry",
		});
	});

	it("shows actionable structured failure details", async () => {
		renderPage();

		expect(await screen.findByText("VIDEO_SOURCE_MISSING")).toBeInTheDocument();
		expect(
			screen.getByText("No usable video source is available."),
		).toBeInTheDocument();
		// The failed phase label uses the Chinese display name from PIPELINE_STEPS
		expect(screen.getByText(/底包拼接/)).toBeInTheDocument();
		expect(screen.getByText(/不可重试/)).toBeInTheDocument();
	});

	it("shows retry request failures for retryable errors", async () => {
		// Use a retryable error so the retry button appears
		vi.mocked(api.getJob).mockResolvedValue({
			...failedJob,
			execution: {
				...failedJob.execution,
				error: {
					code: "MEDIA_PROCESSING_TIMEOUT",
					message: "Processing timed out.",
					retryable: true,
				},
			},
		} as never);
		vi.mocked(api.retryJob).mockRejectedValue(new Error("still invalid"));

		renderPage();

		const retryBtn = await screen.findByRole("button", {
			name: "重试失败阶段",
		});
		fireEvent.click(retryBtn);

		// Non-structured errors trigger the fallback message from formatRetryError
		expect(await screen.findByText(/重试前验证失败/)).toBeInTheDocument();
	});

	it("surfaces structured 409 revalidation detail from the server", async () => {
		// Use a retryable error so the retry button appears
		vi.mocked(api.getJob).mockResolvedValue({
			...failedJob,
			execution: {
				...failedJob.execution,
				error: {
					code: "VIDEO_SOURCE_MISSING",
					message: "No usable video source is available.",
					retryable: true,
				},
			},
		} as never);
		vi.mocked(api.retryJob).mockRejectedValue(
			new Error(
				`409: ${JSON.stringify({
					detail: {
						code: "VIDEO_SOURCE_MISSING",
						message: "No usable video source is available.",
						retryable: false,
					},
				})}`,
			),
		);

		renderPage();

		const retryBtn = await screen.findByRole("button", {
			name: "重试失败阶段",
		});
		fireEvent.click(retryBtn);

		expect(
			await screen.findByText(
				"重试前验证失败：No usable video source is available.（VIDEO_SOURCE_MISSING）",
			),
		).toBeInTheDocument();
	});

	it("shows bounded retry progress while the phase remains active", async () => {
		vi.mocked(api.getJob).mockResolvedValue({
			...failedJob,
			phase: "video_rendering",
			failed_phase: undefined,
			execution: {
				status: "retrying",
				current_attempt: 2,
				max_attempts: 3,
				error: null,
			},
		});
		renderPage();

		expect(
			await screen.findByText(/正在重试，第 2 \/ 3 次/),
		).toBeInTheDocument();
	});
});

describe("JobPipeline migration_required workflow", () => {
	const migrationJob = {
		job_id: "job-migration",
		project_id: "project-1",
		product: "product",
		platforms: ["douyin"],
		phase: "migration_required" as const,
		failed_phase: null,
		review_status: "none" as const,
		artifacts: [],
		execution: {
			status: "failed" as const,
			current_attempt: 1,
			max_attempts: 3,
			error: {
				code: "SCENE_INPUT_MISSING",
				message: "missing scene input",
				retryable: false as const,
			},
		},
	};

	function renderMigrationPage() {
		return render(
			<MemoryRouter initialEntries={["/jobs/job-migration"]}>
				<Routes>
					<Route path="/jobs/:id" element={<JobPipeline />} />
				</Routes>
			</MemoryRouter>,
		);
	}

	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getJob).mockResolvedValue(migrationJob);
		vi.mocked(api.migrateScenes).mockResolvedValue({
			status: "migrated",
			phase: "queued",
			job_id: "job-migration",
		});
		vi.mocked(api.getSceneFolders).mockResolvedValue({
			folders: [{ name: "场景一", path: "scenes/one" }],
		});
	});

	it("shows scene folder selector and allows migration", async () => {
		renderMigrationPage();

		expect(await screen.findByText("需补充场景文件夹")).toBeInTheDocument();
		expect(await screen.findByLabelText("场景一")).toBeInTheDocument();

		fireEvent.click(screen.getByLabelText("场景一"));
		fireEvent.click(
			screen.getByRole("button", { name: "补充场景并重新启动任务" }),
		);

		await waitFor(() => {
			expect(api.migrateScenes).toHaveBeenCalledWith("job-migration", [
				"scenes/one",
			]);
		});
	});

	it("shows explicit rebuild/migration guidance text", async () => {
		renderMigrationPage();

		expect(await screen.findByText(/历史创建/)).toBeInTheDocument();
		expect(screen.getByText(/缺少有效的场景输入/)).toBeInTheDocument();
		expect(
			screen.getByText(/系统将重建任务并保留现有文案与配置/),
		).toBeInTheDocument();
	});
});

describe("JobPipeline TTS voice selection (#177)", () => {
	const ttsGenJob = {
		job_id: "job-tts-1",
		project_id: "project-1",
		product: "product",
		platforms: ["douyin"],
		phase: "tts_generating" as const,
		failed_phase: null,
		review_status: "none" as const,
		artifacts: [],
		execution: {
			status: "succeeded" as const,
			current_attempt: 1,
			max_attempts: 3,
			error: null,
		},
		tts_model: "",
		tts_voice: "",
		mode: "generate" as const,
	};

	function renderTtsPage() {
		return render(
			<MemoryRouter initialEntries={["/jobs/job-tts-1"]}>
				<Routes>
					<Route path="/jobs/:id" element={<JobPipeline />} />
				</Routes>
			</MemoryRouter>,
		);
	}

	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getJob).mockResolvedValue(ttsGenJob);
		vi.mocked(api.getTTSVoices).mockResolvedValue({
			preset_voices: [
				{
					id: "Cherry",
					label: "芊悦",
					note: "阳光积极女声",
					model: "qwen3-tts-flash",
				},
				{ id: "Mia", label: "Mia", note: "英文女声", model: "mimo-v2.5-tts" },
				{ id: "Dean", label: "Dean", note: "英文男声", model: "mimo-v2.5-tts" },
			],
		});
		vi.mocked(api.getJobTTSVoice).mockResolvedValue({
			model: "mimo-v2.5-tts",
			voice: "Mia",
			resolved_from: "global",
		});
		vi.mocked(api.updateJobTTSVoice).mockResolvedValue({
			model: "mimo-v2.5-tts",
			voice: "Dean",
			resolved_from: "job",
		});
		vi.mocked(api.previewJobTTS).mockResolvedValue("blob:preview-audio");
	});

	it("renders TTS voice selector with available voices", async () => {
		renderTtsPage();

		expect(await screen.findByText("TTS 配音")).toBeInTheDocument();
		expect(await screen.findByText(/全局/)).toBeInTheDocument();
	});

	it("renders preview button and calls preview API", async () => {
		renderTtsPage();

		const previewBtn = await screen.findByRole("button", { name: /试听/ });
		expect(previewBtn).toBeInTheDocument();

		fireEvent.click(previewBtn);
		await waitFor(() => {
			expect(api.previewJobTTS).toHaveBeenCalledWith("job-tts-1");
		});
	});

	it("shows link to global TTS config page", async () => {
		renderTtsPage();

		const link = await screen.findByText(/高级 TTS 配置/);
		expect(link).toBeInTheDocument();
		expect(link.closest("a")?.getAttribute("href")).toBe("/tts-config");
	});
});

describe("JobPipeline asset phase states", () => {
	const assetRetrievingBase = {
		job_id: "job-asset-1",
		project_id: "project-1",
		product: "product",
		platforms: ["douyin"],
		phase: "asset_retrieving" as const,
		failed_phase: null,
		review_status: "none" as const,
		artifacts: [],
		mode: "generate" as const,
	};

	function renderAssetPage() {
		return render(
			<MemoryRouter initialEntries={["/jobs/job-asset-1"]}>
				<Routes>
					<Route path="/jobs/:id" element={<JobPipeline />} />
				</Routes>
			</MemoryRouter>,
		);
	}

	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("shows asset_retrieving pending state: waiting to start", async () => {
		vi.mocked(api.getJob).mockResolvedValue({
			...assetRetrievingBase,
			execution: {
				status: "pending",
				current_attempt: 0,
				max_attempts: 3,
				error: null,
			},
		} as never);

		renderAssetPage();

		expect(await screen.findByText("等待开始切配...")).toBeInTheDocument();
	});

	it("shows asset_retrieving running state with attempt info", async () => {
		vi.mocked(api.getJob).mockResolvedValue({
			...assetRetrievingBase,
			execution: {
				status: "running",
				current_attempt: 1,
				max_attempts: 3,
				error: null,
			},
		} as never);

		renderAssetPage();

		expect(await screen.findByText("正在切配素材...")).toBeInTheDocument();
		expect(screen.getByText(/1 \/ 3/)).toBeInTheDocument();
	});

	it("shows asset_retrieving no-assets state when succeeded but no clip artifact", async () => {
		vi.mocked(api.getJob).mockResolvedValue({
			...assetRetrievingBase,
			execution: {
				status: "succeeded",
				current_attempt: 1,
				max_attempts: 3,
				error: null,
			},
		} as never);

		renderAssetPage();

		expect(await screen.findByText("无可用素材")).toBeInTheDocument();
		expect(screen.getByText(/未找到与当前文案匹配的素材/)).toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: "重新检索素材" }),
		).toBeInTheDocument();
	});

	it("shows asset_retrieving succeeded with clips artifact and asset grid", async () => {
		vi.mocked(api.getJob).mockResolvedValue({
			...assetRetrievingBase,
			artifacts: [
				{
					kind: "selected_clips",
					relative_path: "clips.json",
					url: "/api/workspace/projects/project-1/runtime/jobs/job-asset-1/clips.json",
				},
			],
			execution: {
				status: "succeeded",
				current_attempt: 1,
				max_attempts: 3,
				error: null,
			},
		} as never);

		renderAssetPage();

		// When clips artifact exists, we show "已检索到 N 个匹配素材"
		expect(await screen.findByText(/已检索到/)).toBeInTheDocument();
		expect(screen.getByText(/个匹配素材/)).toBeInTheDocument();
	});

	it("shows failed asset retrieval with retryable error and retry button", async () => {
		vi.mocked(api.getJob).mockResolvedValue({
			...assetRetrievingBase,
			phase: "failed",
			failed_phase: "asset_retrieving",
			execution: {
				status: "failed",
				current_attempt: 2,
				max_attempts: 3,
				error: {
					code: "ASSET_SEARCH_FAILED",
					message: "素材检索服务暂时不可用",
					retryable: true,
				},
			},
		} as never);
		vi.mocked(api.retryJob).mockResolvedValue({
			status: "phase_queued_for_retry",
		});

		renderAssetPage();

		expect(
			await screen.findByText("素材检索失败（可重试）"),
		).toBeInTheDocument();
		expect(screen.getByText("ASSET_SEARCH_FAILED")).toBeInTheDocument();
		expect(
			screen.getByRole("button", { name: "重试失败阶段" }),
		).toBeInTheDocument();
	});

	it("shows failed asset retrieval with terminal error and no retry button", async () => {
		vi.mocked(api.getJob).mockResolvedValue({
			...assetRetrievingBase,
			phase: "failed",
			failed_phase: "asset_retrieving",
			execution: {
				status: "failed",
				current_attempt: 3,
				max_attempts: 3,
				error: {
					code: "ASSET_LIBRARY_EMPTY",
					message: "素材库为空，请先上传素材",
					retryable: false,
				},
			},
		} as never);

		renderAssetPage();

		expect(
			await screen.findByText("素材检索失败（已终止）"),
		).toBeInTheDocument();
		expect(screen.getByText("ASSET_LIBRARY_EMPTY")).toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: "重试失败阶段" }),
		).not.toBeInTheDocument();
		expect(screen.getByText(/不可重试/)).toBeInTheDocument();
	});

	const completedJob = {
		job_id: "job-200",
		project_id: "project-1",
		product: "product",
		platforms: ["douyin"],
		phase: "completed" as const,
		failed_phase: null,
		review_status: "approved" as const,
		artifacts: [
			{
				kind: "final_video",
				url: "/workspace/projects/project-1/runtime/jobs/job-200/final.mp4",
			},
		],
		execution: {
			status: "completed" as const,
			current_attempt: 1,
			max_attempts: 3,
		},
	};

	function renderCompletedPage() {
		return render(
			<MemoryRouter initialEntries={["/jobs/job-200"]}>
				<Routes>
					<Route path="/jobs/:id" element={<JobPipeline />} />
				</Routes>
			</MemoryRouter>,
		);
	}

	describe("JobPipeline async export UI (#255)", () => {
		beforeEach(() => {
			vi.clearAllMocks();
			vi.mocked(api.getJob).mockResolvedValue(completedJob as never);
			vi.mocked(api.getExportStatus).mockResolvedValue(null);
		});

		it("shows export button in completed state", async () => {
			renderCompletedPage();

			expect(await screen.findByText("生产完成")).toBeInTheDocument();
			expect(screen.getByText("导出")).toBeInTheDocument();
		});

		it("shows creating state after clicking export", async () => {
			// Start with no existing task so we see the export button
			let statusCalls = 0;
			vi.mocked(api.getExportStatus).mockImplementation(async () => {
				statusCalls++;
				if (statusCalls === 1) return null;
				return {
					task_id: "task-1",
					status: "queued",
					progress: 0,
					error: null,
				};
			});
			vi.mocked(api.createExport).mockResolvedValue({
				task_id: "task-1",
				status: "queued",
			});

			renderCompletedPage();

			await screen.findByText("导出");
			const btn = screen.getByText("导出");
			fireEvent.click(btn);

			expect(await screen.findByText("排队中...")).toBeInTheDocument();
		});

		it("shows running state with progress", async () => {
			vi.mocked(api.getExportStatus).mockResolvedValue({
				task_id: "task-1",
				status: "running",
				progress: 45,
				error: null,
			});

			renderCompletedPage();

			expect(await screen.findByText("生产完成")).toBeInTheDocument();
			expect(screen.getByText("处理中...")).toBeInTheDocument();
		});

		it("renders the actual zero progress without a visual floor", async () => {
			vi.mocked(api.getExportStatus).mockResolvedValue({
				task_id: "task-1",
				status: "running",
				progress: 0,
				error: null,
			});

			renderCompletedPage();

			const progressbar = await screen.findByRole("progressbar");
			expect(progressbar).toHaveStyle({ width: "0%" });
			expect(progressbar).toHaveAttribute("aria-valuenow", "0");
		});

		it("keeps the created task when the immediate status refresh fails", async () => {
			vi.mocked(api.getExportStatus)
				.mockResolvedValueOnce(null)
				.mockRejectedValueOnce(new Error("status unavailable"));
			vi.mocked(api.createExport).mockResolvedValue({
				task_id: "task-1",
				status: "queued",
			});

			renderCompletedPage();
			fireEvent.click(await screen.findByText("导出"));

			expect(await screen.findByText("排队中...")).toBeInTheDocument();
		});

		it("keeps the current task visible when a polling request fails", async () => {
			vi.mocked(api.getExportStatus)
				.mockResolvedValueOnce({
					task_id: "task-1",
					status: "running",
					progress: 45,
					error: null,
				})
				.mockRejectedValue(new Error("temporary status failure"));

			renderCompletedPage();
			expect(await screen.findByText("45%")).toBeInTheDocument();

			await new Promise((resolve) => setTimeout(resolve, 2100));

			expect(screen.getByText("45%")).toBeInTheDocument();
			expect(screen.queryByText("导出")).not.toBeInTheDocument();
		});

		it("shows download button when ready", async () => {
			vi.mocked(api.getExportStatus).mockResolvedValue({
				task_id: "task-1",
				status: "ready",
				progress: 100,
				error: null,
			});

			renderCompletedPage();

			expect(await screen.findByText("生产完成")).toBeInTheDocument();
			expect(screen.getByText("下载导出包")).toBeInTheDocument();
		});

		it("shows error and re-create action when failed", async () => {
			vi.mocked(api.getExportStatus).mockResolvedValue({
				task_id: "task-1",
				status: "failed",
				progress: 0,
				error: "segment count mismatch: 3 segments for 5 timeline entries",
			});

			renderCompletedPage();

			expect(await screen.findByText("生产完成")).toBeInTheDocument();
			expect(screen.getByText(/segment count mismatch/)).toBeInTheDocument();
			expect(screen.getByText("重新创建")).toBeInTheDocument();
		});

		it("shows stale message with re-create action", async () => {
			vi.mocked(api.getExportStatus).mockResolvedValue({
				task_id: "task-1",
				status: "stale",
				progress: 0,
				error: null,
			});

			renderCompletedPage();

			expect(await screen.findByText("生产完成")).toBeInTheDocument();
			expect(screen.getByText(/已过期/)).toBeInTheDocument();
			expect(screen.getByText("重新创建")).toBeInTheDocument();
		});
	});
});
