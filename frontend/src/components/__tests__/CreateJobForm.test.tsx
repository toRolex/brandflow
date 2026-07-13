import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import CreateJobForm from "../CreateJobForm";
import { api } from "../../api/client";

// Mock the API client
vi.mock("../../api/client", () => ({
  api: {
    getTTSVoices: vi.fn(),
    previewTemplate: vi.fn(),
    generateCoverTitle: vi.fn(),
  },
}));

const MOCK_VOICES = [
  { id: "Mia", label: "Mia", note: "英文女声" },
  { id: "冰糖", label: "冰糖", note: "中文女声，清亮自然" },
  { id: "茉莉", label: "茉莉", note: "中文女声，柔和亲切" },
];

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

describe("CreateJobForm - TTS Voice Selector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getTTSVoices as ReturnType<typeof vi.fn>).mockResolvedValue({
      preset_voices: MOCK_VOICES,
    });
  });

  it("loads TTS voices on mount", async () => {
    render(<CreateJobForm {...defaultProps()} />);

    await waitFor(() => {
      expect(api.getTTSVoices).toHaveBeenCalledTimes(1);
    });
  });

  it("shows voice selector when audio mode is TTS", async () => {
    render(<CreateJobForm {...defaultProps()} />);

    await waitFor(() => {
      // The voice selector label text should be visible
      expect(screen.getByText("TTS 音色")).toBeInTheDocument();
    });

    // Default option should be present
    expect(screen.getByText("-- 使用默认音色 --")).toBeInTheDocument();
  });

  it("shows loaded voices in the dropdown", async () => {
    render(<CreateJobForm {...defaultProps()} />);

    // Wait for voices to load
    await waitFor(() => {
      expect(api.getTTSVoices).toHaveBeenCalledTimes(1);
    });

    // All voice labels should appear in the dropdown
    for (const v of MOCK_VOICES) {
      expect(screen.getByText(v.label)).toBeInTheDocument();
    }
  });

  it("includes selected tts_voice in form data on submit", async () => {
    const onCreateJob = vi.fn();

    const { container } = render(
      <CreateJobForm
        {...defaultProps({
          audioMode: "tts" as const,
          product: "test-product",
          platforms: ["douyin"],
          onCreateJob,
        })}
      />
    );

    // Wait for voices to load
    await waitFor(() => {
      expect(api.getTTSVoices).toHaveBeenCalledTimes(1);
    });

    // Select a voice using the voice dropdown (last select in the form)
    const selects = container.querySelectorAll<HTMLSelectElement>("select");
    const voiceSelect = Array.from(selects).find(
      (s) => s.closest("label")?.textContent?.includes("TTS 音色")
    )!;
    expect(voiceSelect).toBeTruthy();
    fireEvent.change(voiceSelect, { target: { value: "冰糖" } });

    // Click submit
    fireEvent.click(screen.getByText("创建并开始生产"));

    await waitFor(() => {
      expect(onCreateJob).toHaveBeenCalled();
    });

    const formData = onCreateJob.mock.calls[0][0];
    expect(formData.tts_voice).toBe("冰糖");
  });

  it("does not show voice selector when audio mode is upload", () => {
    render(
      <CreateJobForm
        {...defaultProps({
          audioMode: "upload" as const,
        })}
      />
    );

    expect(screen.queryByText("TTS 音色")).not.toBeInTheDocument();
  });

  it("shows voice note when a voice is selected", async () => {
    const { container } = render(<CreateJobForm {...defaultProps()} />);

    await waitFor(() => {
      expect(api.getTTSVoices).toHaveBeenCalledTimes(1);
    });

    // Find the voice dropdown
    const selects = container.querySelectorAll<HTMLSelectElement>("select");
    const voiceSelect = Array.from(selects).find(
      (s) => s.closest("label")?.textContent?.includes("TTS 音色")
    )!;
    expect(voiceSelect).toBeTruthy();
    fireEvent.change(voiceSelect, { target: { value: "冰糖" } });

    expect(screen.getByText("中文女声，清亮自然")).toBeInTheDocument();
  });
});
