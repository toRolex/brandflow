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
			retryable: false,
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
		expect(screen.getByText(/video_rendering/)).toBeInTheDocument();
		expect(screen.getByText(/3 \/ 3/)).toBeInTheDocument();
	});

	it("awaits retry and reloads the recovered phase", async () => {
		renderPage();
		fireEvent.click(
			await screen.findByRole("button", { name: "重试失败阶段" }),
		);

		await waitFor(() => expect(api.retryJob).toHaveBeenCalledWith("job-170"));
		await waitFor(() => expect(api.getJob).toHaveBeenCalledTimes(2));
	});

	it("shows retry request failures", async () => {
		vi.mocked(api.retryJob).mockRejectedValue(new Error("still invalid"));
		renderPage();
		fireEvent.click(
			await screen.findByRole("button", { name: "重试失败阶段" }),
		);

		expect(await screen.findByText("重试前验证失败")).toBeInTheDocument();
	});

	it("surfaces structured 409 revalidation detail from the server", async () => {
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
		fireEvent.click(
			await screen.findByRole("button", { name: "重试失败阶段" }),
		);

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
				retryable: false,
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
		fireEvent.click(screen.getByRole("button", { name: "重新启动任务" }));

		await waitFor(() => {
			expect(api.migrateScenes).toHaveBeenCalledWith("job-migration", [
				"scenes/one",
			]);
		});
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

	function renderTTSPage() {
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
		renderTTSPage();

		// Should show the TTS step title
		expect(await screen.findByText("TTS 配音")).toBeInTheDocument();

		// Should show resolution badge
		expect(await screen.findByText(/全局/)).toBeInTheDocument();
	});

	it("renders preview button and calls preview API", async () => {
		renderTTSPage();

		const previewBtn = await screen.findByRole("button", { name: /试听/ });
		expect(previewBtn).toBeInTheDocument();

		fireEvent.click(previewBtn);
		await waitFor(() => {
			expect(api.previewJobTTS).toHaveBeenCalledWith("job-tts-1");
		});
	});

	it("shows link to global TTS config page", async () => {
		renderTTSPage();

		const link = await screen.findByText(/高级 TTS 配置/);
		expect(link).toBeInTheDocument();
		expect(link.closest("a")?.getAttribute("href")).toBe("/tts-config");
	});
});
