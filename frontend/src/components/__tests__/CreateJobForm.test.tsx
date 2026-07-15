import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import CreateJobForm from "../CreateJobForm";

// Mock the API client
vi.mock("../../api/client", () => ({
  api: {
    previewTemplate: vi.fn(),
    generateCoverTitle: vi.fn(),
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
      <CreateJobForm
        {...defaultProps({ audioMode: "upload" as const })}
      />
    );

    expect(screen.getByText("点击选择音频文件")).toBeInTheDocument();
    expect(screen.queryByText("TTS 生成")).toBeInTheDocument();
  });

  it("hides file upload UI when audio mode is TTS", () => {
    render(
      <CreateJobForm
        {...defaultProps({ audioMode: "tts" as const })}
      />
    );

    expect(screen.queryByText("点击选择音频文件")).not.toBeInTheDocument();
  });

  it("calls setAudioMode when radio button is clicked", () => {
    const setAudioMode = vi.fn();
    render(
      <CreateJobForm
        {...defaultProps({ setAudioMode, audioMode: "tts" as const })}
      />
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
      />
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
      />
    );

    expect(screen.getByText("voice-over.mp3")).toBeInTheDocument();
  });
});

