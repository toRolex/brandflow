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

function renderWithJob(job: Record<string, unknown>) {
	return render(
		<MemoryRouter initialEntries={[`/jobs/${job.job_id}`]}>
			<Routes>
				<Route path="/jobs/:id" element={<JobPipeline />} />
			</Routes>
		</MemoryRouter>,
	);
}

const baseTtsJob = {
	job_id: "job-ts-1",
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

// ---------------------------------------------------------------------------
// Scope #252: TTS model+voice atomicity
// ---------------------------------------------------------------------------

describe("TTS model switch clears voice (#252)", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getJob).mockResolvedValue(baseTtsJob);
		vi.mocked(api.getTTSVoices).mockResolvedValue({
			preset_voices: [
				{ id: "Mia", label: "Mia", note: "EN-F", model: "mimo-v2.5-tts" },
				{ id: "Dean", label: "Dean", note: "EN-M", model: "mimo-v2.5-tts" },
			],
		});
		vi.mocked(api.getJobTTSVoice).mockResolvedValue({
			model: "mimo-v2.5-tts",
			voice: "Mia",
			resolved_from: "global",
			product: "test-product",
		});
	});

	it("re-fetches voices when model dropdown changes", async () => {
		renderWithJob(baseTtsJob);

		await screen.findByRole("heading", { name: /TTS/ });

		await waitFor(() => expect(api.getTTSVoices).toHaveBeenCalled());

		// Find the first select (model selector) — there may be multiple <option> with same value
		const selects = screen.getAllByRole("combobox");
		const modelSelect = selects[0];
		fireEvent.change(modelSelect, { target: { value: "qwen3-tts-flash" } });

		await waitFor(() => {
			expect(api.getTTSVoices).toHaveBeenCalledWith(
				undefined,
				"qwen3-tts-flash",
			);
		});
	});
});

describe("TTS controls hidden for upload audio (#252)", () => {
	const uploadJob = {
		...baseTtsJob,
		job_id: "job-up-1",
		audio_source: "upload" as const,
	};

	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getJob).mockResolvedValue(uploadJob);
		vi.mocked(api.getTTSVoices).mockResolvedValue({ preset_voices: [] });
		vi.mocked(api.getJobTTSVoice).mockResolvedValue({
			model: "mimo-v2.5-tts",
			voice: "Mia",
			resolved_from: "global",
			product: "test-product",
		});
	});

	it("shows audio-not-applicable message instead of TTS controls", async () => {
		renderWithJob(uploadJob);

		await screen.findByRole("heading", { name: /TTS/ });
		expect(await screen.findByText(/已有/)).toBeInTheDocument();
		expect(screen.queryByText(/当前音色/)).not.toBeInTheDocument();
	});
});

describe("TTS inline validation error (#252)", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getJob).mockResolvedValue(baseTtsJob);
		vi.mocked(api.getTTSVoices).mockResolvedValue({
			preset_voices: [
				{ id: "Mia", label: "Mia", note: "EN-F", model: "mimo-v2.5-tts" },
			],
		});
		vi.mocked(api.getJobTTSVoice).mockResolvedValue({
			model: "mimo-v2.5-tts",
			voice: "Mia",
			resolved_from: "global",
			product: "test-product",
		});
	});

	it("shows inline validation error when TTS save fails with 422", async () => {
		vi.mocked(api.updateJobTTSVoice).mockRejectedValue(
			new Error(`422: {"detail":"invalid voice for model"}`),
		);
		renderWithJob(baseTtsJob);

		await screen.findByRole("heading", { name: /TTS/ });

		const applyBtn = await screen.findByRole("button", { name: "应用" });
		fireEvent.click(applyBtn);

		await waitFor(() => {
			expect(screen.getByText(/invalid voice/)).toBeInTheDocument();
		});
	});
});

// ---------------------------------------------------------------------------
// Scope #269: TTS effective config visibility
// ---------------------------------------------------------------------------

describe("TTS effective config visibility (#269)", () => {
	it("shows the effective TTS config with product and job override", async () => {
		vi.clearAllMocks();
		const jobWithOverride = {
			...baseTtsJob,
			product: "product" as const,
			tts_model: "qwen3-tts-flash" as const,
			tts_voice: "Cherry" as const,
		};
		vi.mocked(api.getJob).mockResolvedValue(jobWithOverride);
		vi.mocked(api.getTTSVoices).mockResolvedValue({ preset_voices: [] });
		vi.mocked(api.getJobTTSVoice).mockResolvedValue({
			model: "qwen3-tts-flash",
			voice: "Cherry",
			resolved_from: "job",
			product: "product",
		});

		renderWithJob(jobWithOverride);

		await screen.findByRole("heading", { name: /TTS/ });
		expect(await screen.findByText("所属产品：product")).toBeInTheDocument();
		expect(screen.getByText("Job 覆盖")).toBeInTheDocument();
		expect(screen.getByText("qwen3-tts-flash / Cherry")).toBeInTheDocument();
	});

	it("shows product-level attribution when no job override is set", async () => {
		vi.clearAllMocks();
		const jobWithProduct = {
			...baseTtsJob,
			product: "product" as const,
			tts_model: "" as const,
			tts_voice: "" as const,
		};
		vi.mocked(api.getJob).mockResolvedValue(jobWithProduct);
		vi.mocked(api.getTTSVoices).mockResolvedValue({ preset_voices: [] });
		vi.mocked(api.getJobTTSVoice).mockResolvedValue({
			model: "mimo-v2.5-tts",
			voice: "Mia",
			resolved_from: "product",
			product: "product",
		});

		renderWithJob(jobWithProduct);

		await screen.findByRole("heading", { name: /TTS/ });
		expect(await screen.findByText("所属产品：product")).toBeInTheDocument();
		expect(screen.getByText("产品")).toBeInTheDocument();
		expect(screen.getByText("mimo-v2.5-tts / Mia")).toBeInTheDocument();
	});
});
