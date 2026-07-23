import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import { ProductProvider } from "../../ProductContext";
import TtsConfigPage from "../TTSConfig";

vi.mock("../../api/client", () => ({
	api: {
		getTTSConfig: vi.fn(),
		saveTTSConfig: vi.fn(),
		getTTSVoices: vi.fn(),
		previewTTS: vi.fn(),
		listProducts: vi.fn(),
		getProductConfig: vi.fn(),
		switchProduct: vi.fn(),
		createProduct: vi.fn(),
		renameProduct: vi.fn(),
		deleteProduct: vi.fn(),
	},
}));

const baseConfig = {
	model: "qwen3-tts-flash",
	voice: "Cherry",
	fallback_voice: "Mia",
	randomize_voice: false,
	random_voices: [] as string[],
	voice_design_prompt: "",
	style_control_mode: "simple",
	style_prompt: "",
	director_character: "",
	director_scene: "",
	director_guidance: "",
	audio_tags_enabled: false,
	audio_tags: "",
	audio_format: "wav",
	instructions: "",
	optimize_instructions: false,
	language_type: "Chinese",
	voice_clone_sample_path: null,
	voice_clone_mime_type: null,
	optimize_text_preview: false,
};

const mimoConfig = {
	model: "mimo-v2.5-tts",
	voice: "Mia",
	fallback_voice: "Dean",
	randomize_voice: false,
	random_voices: [] as string[],
	voice_design_prompt: "",
	style_control_mode: "simple",
	style_prompt: "",
	director_character: "",
	director_scene: "",
	director_guidance: "",
	audio_tags_enabled: false,
	audio_tags: "",
	audio_format: "wav",
	instructions: "",
	optimize_instructions: false,
	language_type: "Chinese",
	voice_clone_sample_path: null,
	voice_clone_mime_type: null,
	optimize_text_preview: false,
};

interface ProductSummary {
	id: string;
	name: string;
}

function renderWithProduct(
	activeProduct: ProductSummary = { id: "prod-a", name: "夏日凉感" },
	products: ProductSummary[] = [activeProduct],
) {
	vi.mocked(api.listProducts).mockResolvedValue(products);
	vi.mocked(api.getProductConfig).mockResolvedValue({
		id: activeProduct.id,
		default_name: activeProduct.name,
		default_brand: "测试品牌",
		script: {
			scene: "",
			material: "",
			system_prompt: "",
		},
	});
	render(
		<ProductProvider>
			<TtsConfigPage />
		</ProductProvider>,
	);
}

describe("TTSConfig product scope label", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("shows the active product name", async () => {
		vi.mocked(api.getTTSConfig).mockResolvedValue(baseConfig);
		vi.mocked(api.getTTSVoices).mockResolvedValue({ preset_voices: [] });

		renderWithProduct({ id: "prod-a", name: "夏日凉感" });

		await waitFor(() => expect(api.getTTSConfig).toHaveBeenCalled());
		expect(
			await screen.findByText(/正在编辑产品「夏日凉感」的 TTS 配置/),
		).toBeInTheDocument();
	});

	it("falls back to the active product id when name is empty", async () => {
		vi.mocked(api.getTTSConfig).mockResolvedValue(baseConfig);
		vi.mocked(api.getTTSVoices).mockResolvedValue({ preset_voices: [] });

		renderWithProduct({ id: "prod-b", name: "" });

		await waitFor(() => expect(api.getTTSConfig).toHaveBeenCalled());
		expect(
			await screen.findByText(/正在编辑产品「prod-b」的 TTS 配置/),
		).toBeInTheDocument();
	});

	it("shows global label when no active product is selected", async () => {
		vi.mocked(api.getTTSConfig).mockResolvedValue(baseConfig);
		vi.mocked(api.getTTSVoices).mockResolvedValue({ preset_voices: [] });

		renderWithProduct({ id: "", name: "" }, []);

		await waitFor(() => expect(api.getTTSConfig).toHaveBeenCalled());
		expect(await screen.findByText(/全局 TTS 配置/)).toBeInTheDocument();
	});
});

// ---------------------------------------------------------------------------
// Scope #323: TTS model switch preserves voice or falls back to Cherry
// ---------------------------------------------------------------------------

describe("TTSConfigPage model switch preserves voice or falls back to Cherry (#323)", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("keeps current voice when it exists in the new model preset", async () => {
		vi.mocked(api.getTTSConfig).mockResolvedValue(mimoConfig);
		vi.mocked(api.getTTSVoices).mockImplementation(
			(_provider?: string, model?: string) => {
				if (model?.startsWith("qwen")) {
					return Promise.resolve({
						preset_voices: [
							{ id: "Cherry", label: "芊悦", note: "女声", model: "qwen3-tts-flash" },
							{ id: "Rocky", label: "阿强", note: "粤语男声", model: "qwen3-tts-flash" },
							{ id: "Mia", label: "乖小妹", note: "女声", model: "qwen3-tts-flash" },
						],
					});
				}
				return Promise.resolve({
					preset_voices: [
						{ id: "冰糖", label: "冰糖", note: "女声", model: "mimo-v2.5-tts" },
						{ id: "Mia", label: "Mia", note: "EN-F", model: "mimo-v2.5-tts" },
					],
				});
			},
		);

		renderWithProduct();

		// Wait for initial load
		await waitFor(() => {
			expect(api.getTTSConfig).toHaveBeenCalled();
		});
		await waitFor(() => {
			expect(api.getTTSVoices).toHaveBeenCalledWith(undefined, "mimo-v2.5-tts");
		});

		// Switch model to Qwen Flash by clicking the card
		fireEvent.click(screen.getByText("Qwen Flash"));

		// Wait for voices to be fetched for the new model
		await waitFor(() => {
			expect(api.getTTSVoices).toHaveBeenCalledWith(undefined, "qwen3-tts-flash");
		});

		// Voice "Mia" exists in Qwen voices → preserved
		await waitFor(() => {
			const voiceSelect = screen.getAllByRole("combobox")[0];
			expect(voiceSelect).toHaveValue("Mia");
		});
	});

	it("falls back to Cherry when current voice is not in the new model preset", async () => {
		const mimoBingtangConfig = {
			...mimoConfig,
			voice: "冰糖",
		};
		vi.mocked(api.getTTSConfig).mockResolvedValue(mimoBingtangConfig);
		vi.mocked(api.getTTSVoices).mockImplementation(
			(_provider?: string, model?: string) => {
				if (model?.startsWith("qwen")) {
					return Promise.resolve({
						preset_voices: [
							{ id: "Cherry", label: "芊悦", note: "女声", model: "qwen3-tts-flash" },
							{ id: "Rocky", label: "阿强", note: "粤语男声", model: "qwen3-tts-flash" },
						],
					});
				}
				return Promise.resolve({
					preset_voices: [
						{ id: "冰糖", label: "冰糖", note: "女声", model: "mimo-v2.5-tts" },
						{ id: "Mia", label: "Mia", note: "EN-F", model: "mimo-v2.5-tts" },
					],
				});
			},
		);

		renderWithProduct();

		await waitFor(() => {
			expect(api.getTTSConfig).toHaveBeenCalled();
		});
		await waitFor(() => {
			expect(api.getTTSVoices).toHaveBeenCalledWith(undefined, "mimo-v2.5-tts");
		});

		// Switch model to Qwen Flash
		fireEvent.click(screen.getByText("Qwen Flash"));

		await waitFor(() => {
			expect(api.getTTSVoices).toHaveBeenCalledWith(undefined, "qwen3-tts-flash");
		});

		// "冰糖" is not in Qwen voices → falls back to "Cherry"
		await waitFor(() => {
			const voiceSelect = screen.getAllByRole("combobox")[0];
			expect(voiceSelect).toHaveValue("Cherry");
		});
	});
});
