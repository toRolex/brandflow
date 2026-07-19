import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import CreateJobForm from "../CreateJobForm";

// Mock the API client
vi.mock("../../api/client", () => ({
	api: {
		previewTemplate: vi.fn(),
		generateCoverTitle: vi.fn(),
		getSceneFolders: vi.fn(() => Promise.resolve({ folders: [] })),
	},
}));

function defaultProps(overrides: Record<string, unknown> = {}) {
	return {
		product: "",
		setProduct: vi.fn(),
		brand: "",
		setBrand: vi.fn(),
		platforms: [],
		togglePlatform: vi.fn(),
		jobName: "",
		setJobName: vi.fn(),
		productionMode: "import" as const,
		setProductionMode: vi.fn(),
		language: "mandarin" as const,
		setLanguage: vi.fn(),
		skipSubtitle: false,
		setSkipSubtitle: vi.fn(),
		manualScript: "",
		setManualScript: vi.fn(),
		audioMode: "tts" as const,
		setAudioMode: vi.fn(),
		audioFile: null,
		setAudioFile: vi.fn(),
		musicTracks: [],
		selectedMusic: "",
		setSelectedMusic: vi.fn(),
		musicVolume: 80,
		setMusicVolume: vi.fn(),
		coverTitleText: "",
		setCoverTitleText: vi.fn(),
		coverHighlightWords: "",
		setCoverHighlightWords: vi.fn(),
		sceneFolderIds: [],
		setSceneFolderIds: vi.fn(),
		templates: [],
		selectedTemplateId: "",
		setSelectedTemplateId: vi.fn(),
		templateVariableValues: {},
		setTemplateVariableValues: vi.fn(),
		showTemplateSection: false,
		setShowTemplateSection: vi.fn(),
		handleSelectTemplate: vi.fn(),
		onCreateJob: vi.fn(),
		onError: vi.fn(),
		...overrides,
	};
}

describe("CreateJobForm - Audio Source Switching", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("shows TTS and Upload radio buttons by default", () => {
		render(<CreateJobForm {...defaultProps()} />);

		expect(screen.getByLabelText("TTS 生成")).toBeInTheDocument();
		expect(screen.getByLabelText("上传音频")).toBeInTheDocument();
	});

	it("defaults to TTS mode", () => {
		render(<CreateJobForm {...defaultProps()} />);

		const ttsRadio = screen.getByLabelText("TTS 生成") as HTMLInputElement;
		expect(ttsRadio.checked).toBe(true);
	});

	it("shows file upload UI when audio mode is upload", () => {
		render(
			<CreateJobForm {...defaultProps({ audioMode: "upload" as const })} />,
		);

		expect(screen.getByText("点击选择音频文件")).toBeInTheDocument();
		expect(screen.queryByText("TTS 生成")).toBeInTheDocument();
	});

	it("hides file upload UI when audio mode is TTS", () => {
		render(<CreateJobForm {...defaultProps({ audioMode: "tts" as const })} />);

		expect(screen.queryByText("点击选择音频文件")).not.toBeInTheDocument();
	});

	it("calls setAudioMode when radio button is clicked", () => {
		const setAudioMode = vi.fn();
		render(
			<CreateJobForm
				{...defaultProps({ setAudioMode, audioMode: "tts" as const })}
			/>,
		);

		fireEvent.click(screen.getByLabelText("上传音频"));
		expect(setAudioMode).toHaveBeenCalledWith("upload");
	});

	it("includes audio_source in form data on submit", async () => {
		const onCreateJob = vi.fn();
		render(
			<CreateJobForm
				{...defaultProps({
					audioMode: "tts" as const,
					product: "test-product",
					platforms: ["douyin"],
					onCreateJob,
				})}
			/>,
		);

		fireEvent.click(screen.getByText("创建并开始生产"));

		await waitFor(() => {
			expect(onCreateJob).toHaveBeenCalled();
		});

		const formData = onCreateJob.mock.calls[0][0];
		expect(formData.audio_source).toBe("tts");
	});

	it("shows selected file name when file is chosen", () => {
		const file = new File(["dummy"], "voice-over.mp3", { type: "audio/mp3" });
		render(
			<CreateJobForm
				{...defaultProps({
					audioMode: "upload" as const,
					audioFile: file,
				})}
			/>,
		);

		expect(screen.getByText("voice-over.mp3")).toBeInTheDocument();
	});
});

describe("CreateJobForm - Generate mode manual script", () => {
	it("shows script textarea in generate mode", () => {
		render(
			<CreateJobForm
				{...defaultProps({
					productionMode: "generate" as const,
				})}
			/>,
		);

		expect(
			screen.getByPlaceholderText("请输入文案内容（150-200字）..."),
		).toBeInTheDocument();
	});

	it("submits manual_script when provided in generate mode", async () => {
		const onCreateJob = vi.fn();
		const setManualScript = vi.fn();
		render(
			<CreateJobForm
				{...defaultProps({
					productionMode: "generate" as const,
					product: "test-product",
					platforms: ["douyin"],
					manualScript: "这是智能生成模式下的手动文案",
					setManualScript,
					onCreateJob,
				})}
			/>,
		);

		fireEvent.click(screen.getByText("创建并开始生产"));

		await waitFor(() => {
			expect(onCreateJob).toHaveBeenCalled();
		});

		const formData = onCreateJob.mock.calls[0][0];
		expect(formData.mode).toBe("generate");
		expect(formData.manual_script).toBe("这是智能生成模式下的手动文案");
	});
});

describe("CreateJobForm - Cover Title Button", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("disables cover title button when manualScript is empty", () => {
		render(
			<CreateJobForm
				{...defaultProps({ productionMode: "import", manualScript: "" })}
			/>,
		);
		const btn = screen.getByText("自动生成标题");
		expect(btn).toBeDisabled();
	});

	it("enables cover title button when manualScript has text", () => {
		render(
			<CreateJobForm
				{...defaultProps({ productionMode: "import", manualScript: "有文案" })}
			/>,
		);
		const btn = screen.getByText("自动生成标题");
		expect(btn).not.toBeDisabled();
	});

	it("shows auto-generate button text when script is non-empty in generate mode", () => {
		render(
			<CreateJobForm
				{...defaultProps({
					productionMode: "generate",
					manualScript: "有文案",
				})}
			/>,
		);
		expect(screen.getByText("自动生成标题")).toBeInTheDocument();
		expect(screen.getByText("自动生成标题")).not.toBeDisabled();
	});

	it("has correct title attribute when disabled due to empty script", () => {
		render(<CreateJobForm {...defaultProps({ manualScript: "" })} />);
		const btn = screen.getByText("自动生成标题");
		expect(btn).toHaveAttribute("title", "需先输入文案才能生成");
	});
});

describe("CreateJobForm - Scene Folder Selection", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("shows scene folder checkboxes in import mode", async () => {
		vi.mocked(api.getSceneFolders).mockResolvedValue({
			folders: [
				{ name: "场景一", path: "scenes/one" },
				{ name: "场景二", path: "scenes/two" },
			],
		});

		render(<CreateJobForm {...defaultProps({ productionMode: "import" })} />);

		await waitFor(() => {
			expect(screen.getByLabelText("场景一")).toBeInTheDocument();
		});
		expect(screen.getByLabelText("场景二")).toBeInTheDocument();
	});

	it("submits selected scene_folder_ids in import mode", async () => {
		vi.mocked(api.getSceneFolders).mockResolvedValue({
			folders: [{ name: "场景一", path: "scenes/one" }],
		});
		const setSceneFolderIds = vi.fn();
		const onCreateJob = vi.fn();

		render(
			<CreateJobForm
				{...defaultProps({
					productionMode: "import",
					product: "test-product",
					platforms: ["douyin"],
					sceneFolderIds: ["scenes/one"],
					setSceneFolderIds,
					onCreateJob,
				})}
			/>,
		);

		await waitFor(() => {
			expect(screen.getByLabelText("场景一")).toBeInTheDocument();
		});

		fireEvent.click(screen.getByText("创建并开始生产"));

		await waitFor(() => {
			expect(onCreateJob).toHaveBeenCalled();
		});

		const formData = onCreateJob.mock.calls[0][0];
		expect(formData.scene_folder_ids).toEqual(["scenes/one"]);
	});
});

describe("CreateJobForm - Mode Switch", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("keeps script textarea visible when switching production mode", () => {
		const { rerender } = render(
			<CreateJobForm
				{...defaultProps({
					productionMode: "import",
					manualScript: "一段文案",
				})}
			/>,
		);

		expect(
			screen.getByPlaceholderText("请输入文案内容（150-200字）..."),
		).toBeInTheDocument();

		// Switch to generate
		rerender(
			<CreateJobForm
				{...defaultProps({
					productionMode: "generate",
					manualScript: "一段文案",
				})}
			/>,
		);

		expect(
			screen.getByPlaceholderText("请输入文案内容（150-200字）..."),
		).toBeInTheDocument();

		// Switch back to import
		rerender(
			<CreateJobForm
				{...defaultProps({
					productionMode: "import",
					manualScript: "一段文案",
				})}
			/>,
		);

		expect(
			screen.getByPlaceholderText("请输入文案内容（150-200字）..."),
		).toBeInTheDocument();
	});
});
