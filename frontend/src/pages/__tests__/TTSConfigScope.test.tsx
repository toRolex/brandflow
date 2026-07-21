import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import { ProductProvider } from "../../ProductContext";
import TTSConfigPage from "../TTSConfig";

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
	});
	render(
		<ProductProvider>
			<TTSConfigPage />
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
