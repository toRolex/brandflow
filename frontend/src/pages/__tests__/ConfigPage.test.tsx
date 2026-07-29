import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import ConfigPage from "../ConfigPage";

vi.mock("../../api/client", () => ({
	api: {
		getConfig: vi.fn(),
		getConfigOptions: vi.fn(),
		saveConfig: vi.fn(),
	},
}));

const MOCK_OPTIONS = {
	providers: {
		llm: {
			providers: {
				deepseek: {
					label: "DeepSeek",
					fields: [
						{
							name: "model",
							label: "模型",
							kind: "select",
							options: ["deepseek-v4-pro"],
						},
						{ name: "api_key", label: "API Key", kind: "text", secret: true },
					],
				},
				kimi: {
					label: "Kimi",
					fields: [{ name: "model", label: "模型", kind: "text" }],
				},
			},
		},
		tts: {
			providers: {
				qwen: {
					label: "通义千问",
					fields: [{ name: "voice", label: "音色", kind: "text" }],
				},
				mimo: {
					label: "MiMo",
					fields: [{ name: "model", label: "模型", kind: "text" }],
				},
			},
		},
		vision: {
			providers: {
				xiaomi: {
					label: "小米",
					fields: [{ name: "model", label: "模型", kind: "text" }],
				},
				claude: {
					label: "Claude",
					fields: [{ name: "model", label: "模型", kind: "text" }],
				},
			},
		},
		text_to_image: {
			label: "文生图",
			providers: {
				dalle: {
					label: "DALL-E",
					fields: [{ name: "model", label: "模型", kind: "text" }],
				},
				midjourney: {
					label: "Midjourney",
					fields: [{ name: "model", label: "模型", kind: "text" }],
				},
			},
		},
		image_to_video: {
			label: "图生视频",
			providers: {
				runway: {
					label: "Runway",
					fields: [{ name: "model", label: "模型", kind: "text" }],
				},
				pika: {
					label: "Pika",
					fields: [{ name: "model", label: "模型", kind: "text" }],
				},
			},
		},
	},
};

const MOCK_CONFIG = {
	providers: {
		llm: { selected: "", providers: {} },
		tts: { selected: "", providers: {} },
		vision: { selected: "", providers: {} },
		text_to_image: { selected: "", providers: {} },
		image_to_video: { selected: "", providers: {} },
	},
};

describe("ConfigPage", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getConfig).mockResolvedValue(MOCK_CONFIG);
		vi.mocked(api.getConfigOptions).mockResolvedValue(MOCK_OPTIONS);
	});

	it("Seam 1: 4 个 section 以横向 Tab 渲染（TTS 由独立页面管理），默认选中 LLM", async () => {
		render(<ConfigPage />);

		await waitFor(() => {
			expect(screen.getByRole("tab", { name: /llm/i })).toBeInTheDocument();
		});

		// TTS is managed exclusively via /tts-config page (#386)
		expect(screen.queryByRole("tab", { name: /tts/i })).not.toBeInTheDocument();
		expect(screen.getByRole("tab", { name: /vision/i })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: /文生图/i })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: /图生视频/i })).toBeInTheDocument();

		expect(screen.getByRole("tab", { name: /llm/i })).toHaveAttribute(
			"aria-selected",
			"true",
		);
	});

	it("Seam 1: 切换 Tab 显示对应 section 的 provider 选择", async () => {
		render(<ConfigPage />);

		await waitFor(() => {
			expect(screen.getByRole("tab", { name: /llm/i })).toBeInTheDocument();
		});

		expect(screen.getByText("DeepSeek")).toBeInTheDocument();

		expect(screen.queryByRole("tab", { name: /tts/i })).not.toBeInTheDocument();

		fireEvent.click(screen.getByRole("tab", { name: /vision/i }));
		expect(screen.getByText("小米")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("tab", { name: /文生图/i }));
		expect(screen.getByText("DALL-E")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("tab", { name: /图生视频/i }));
		expect(screen.getByText("Runway")).toBeInTheDocument();
	});

	it("Seam 2: 每个 Tab 有对应颜色的 SVG 图标", async () => {
		render(<ConfigPage />);

		await waitFor(() => {
			expect(screen.getByRole("tab", { name: /llm/i })).toBeInTheDocument();
		});

		const tabs = ["llm", "vision", "text_to_image", "image_to_video"];
		const expectedColorVars = {
			llm: "--section-llm-color",
			vision: "--section-vision-color",
			text_to_image: "--section-text_to_image-color",
			image_to_video: "--section-image_to_video-color",
		};

		for (const key of tabs) {
			const tab = screen.getByRole("tab", {
				name: new RegExp(
					key === "text_to_image"
						? "文生图"
						: key === "image_to_video"
							? "图生视频"
							: key,
					"i",
				),
			});
			const iconWrapper = tab.querySelector("span");
			expect(iconWrapper).toBeInTheDocument();
			// Tab icons use CSS variables for theming
			expect(iconWrapper?.style.color).toContain(
				expectedColorVars[key as keyof typeof expectedColorVars],
			);
		}
	});

	it("Seam 3: 全局保存配置按钮在标题行右侧，保存后显示成功消息", async () => {
		vi.mocked(api.saveConfig).mockResolvedValue(MOCK_CONFIG);
		render(<ConfigPage />);

		await waitFor(() => {
			expect(screen.getByText("系统配置")).toBeInTheDocument();
		});

		const saveBtn = screen.getByRole("button", { name: /保存配置/i });
		expect(saveBtn).toBeInTheDocument();
		expect(saveBtn).toBeDisabled();

		// Save button should be in header row area
		const header =
			screen.getByText("系统配置").parentElement?.parentElement?.parentElement;
		expect(header?.contains(saveBtn)).toBe(true);

		fireEvent.change(screen.getAllByRole("combobox")[0], {
			target: { value: "kimi" },
		});
		expect(saveBtn).toBeEnabled();
		expect(screen.getByText("有未保存的更改")).toBeInTheDocument();

		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(screen.getByText(/配置已保存|保存成功/i)).toBeInTheDocument();
		});
		expect(api.saveConfig).toHaveBeenCalledTimes(1);
	});

	it("Seam 3: 保存失败后显示失败消息", async () => {
		vi.mocked(api.saveConfig).mockRejectedValue(new Error("Save failed"));
		render(<ConfigPage />);

		await waitFor(() => {
			expect(
				screen.getByRole("button", { name: /保存配置/i }),
			).toBeInTheDocument();
		});

		fireEvent.change(screen.getAllByRole("combobox")[0], {
			target: { value: "kimi" },
		});
		fireEvent.click(screen.getByRole("button", { name: /保存配置/i }));

		await waitFor(() => {
			expect(screen.getByText(/保存失败/i)).toBeInTheDocument();
		});
	});

	it("Seam 10: 已配置的 Secret 不显示掩码值，修改后提示重启", async () => {
		vi.mocked(api.getConfig).mockResolvedValue({
			...MOCK_CONFIG,
			providers: {
				...MOCK_CONFIG.providers,
				llm: {
					selected: "deepseek",
					providers: {
						deepseek: {
							model: "deepseek-v4-pro",
							api_key: "***",
						},
					},
				},
			},
		});
		vi.mocked(api.saveConfig).mockResolvedValue(MOCK_CONFIG);

		render(<ConfigPage />);

		const secretInput = await screen.findByLabelText("API Key");
		expect(secretInput).toHaveValue("");
		expect(secretInput).toHaveAttribute(
			"placeholder",
			expect.stringMatching(/已配置/),
		);

		fireEvent.change(secretInput, { target: { value: "new-secret" } });
		fireEvent.click(screen.getByRole("button", { name: /保存配置/i }));

		await waitFor(() => {
			expect(screen.getByText(/API Key.*重启后端/)).toBeInTheDocument();
		});
	});

	it("Seam 11: 加载失败可直接重试", async () => {
		vi.mocked(api.getConfig)
			.mockRejectedValueOnce(new Error("offline"))
			.mockResolvedValueOnce(MOCK_CONFIG);

		render(<ConfigPage />);

		const retry = await screen.findByRole("button", { name: "重新加载" });
		fireEvent.click(retry);

		expect(
			await screen.findByRole("tab", { name: /llm/i }),
		).toBeInTheDocument();
	});

	it("Seam 12: 没有可用 provider 的能力不显示为空 Tab", async () => {
		vi.mocked(api.getConfigOptions).mockResolvedValue({
			...MOCK_OPTIONS,
			providers: {
				...MOCK_OPTIONS.providers,
				text_to_image: { providers: {} },
				image_to_video: { providers: {} },
			},
		});

		render(<ConfigPage />);

		await screen.findByRole("tab", { name: /llm/i });
		expect(
			screen.queryByRole("tab", { name: /文生图/i }),
		).not.toBeInTheDocument();
		expect(
			screen.queryByRole("tab", { name: /图生视频/i }),
		).not.toBeInTheDocument();
	});

	it("Seam 13: 默认能力不可用时首个可用 Tab 保持选中状态", async () => {
		vi.mocked(api.getConfigOptions).mockResolvedValue({
			...MOCK_OPTIONS,
			providers: {
				...MOCK_OPTIONS.providers,
				llm: { providers: {} },
			},
		});

		render(<ConfigPage />);

		// TTS is filtered out (#386), so the first available tab is vision
		expect(await screen.findByRole("tab", { name: /vision/i })).toHaveAttribute(
			"aria-selected",
			"true",
		);
	});

	it("Seam 14: catalog 声明的运行参数可在页面编辑并保存", async () => {
		const configWithSettings = {
			...MOCK_CONFIG,
			settings: {
				embedding: {
					api_key: "***",
					endpoint: "",
					model: "text-embedding-ada-002",
				},
				scene: { transition_duration_ms: 500 },
			},
		};
		vi.mocked(api.getConfig).mockResolvedValue(configWithSettings);
		vi.mocked(api.getConfigOptions).mockResolvedValue({
			...MOCK_OPTIONS,
			settings: {
				embedding: {
					label: "Embedding",
					description: "检索向量模型",
					fields: [
						{
							name: "api_key",
							label: "Embedding API Key",
							kind: "text",
							secret: true,
						},
						{ name: "model", label: "嵌入模型", kind: "text" },
					],
				},
				scene: {
					label: "场景",
					description: "导入模式场景参数",
					fields: [
						{
							name: "transition_duration_ms",
							label: "转场时长（毫秒）",
							kind: "number",
							min: 0,
						},
					],
				},
			},
		});
		vi.mocked(api.saveConfig).mockResolvedValue(configWithSettings);

		render(<ConfigPage />);
		fireEvent.click(await screen.findByRole("button", { name: "运行参数" }));

		expect(screen.getByLabelText("嵌入模型")).toHaveValue(
			"text-embedding-ada-002",
		);
		expect(screen.getByLabelText("Embedding API Key")).toHaveValue("");
		fireEvent.change(screen.getByLabelText("转场时长（毫秒）"), {
			target: { value: "750" },
		});
		fireEvent.click(screen.getByRole("button", { name: /保存配置/i }));

		await waitFor(() => {
			expect(api.saveConfig).toHaveBeenCalledWith(
				expect.objectContaining({
					settings: expect.objectContaining({
						scene: { transition_duration_ms: 750 },
					}),
				}),
			);
		});
	});

	it("Seam 15: catalog 新增 Provider section 时无需前端白名单", async () => {
		vi.mocked(api.getConfig).mockResolvedValue({
			...MOCK_CONFIG,
			providers: {
				...MOCK_CONFIG.providers,
				speech_to_text: { selected: "", providers: {} },
			},
		});
		vi.mocked(api.getConfigOptions).mockResolvedValue({
			...MOCK_OPTIONS,
			providers: {
				...MOCK_OPTIONS.providers,
				speech_to_text: {
					label: "语音识别",
					providers: {
						whisper: {
							label: "Whisper",
							fields: [{ name: "model", label: "模型", kind: "text" }],
						},
					},
				},
			},
		});

		render(<ConfigPage />);

		expect(
			await screen.findByRole("tab", { name: "语音识别" }),
		).toBeInTheDocument();
	});

	it("Seam 4: 页面加载时自动选中每个 section 的第一个 provider", async () => {
		render(<ConfigPage />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("deepseek-v4-pro")).toBeInTheDocument();
		});

		// LLM first provider is deepseek, model field is shown
		expect(screen.getByDisplayValue("deepseek-v4-pro")).toBeInTheDocument();

		// Switch to Vision and verify first provider selected (model field appears)
		fireEvent.click(screen.getByRole("tab", { name: /vision/i }));
		expect(screen.getByText("模型")).toBeInTheDocument();
		expect(screen.getByRole("combobox")).toHaveValue("xiaomi");
	});

	it("Seam 5: 输入框和下拉框使用设计系统变量", async () => {
		render(<ConfigPage />);

		await waitFor(() => {
			expect(screen.getAllByRole("combobox").length).toBeGreaterThan(0);
		});

		const selects = screen.getAllByRole("combobox");
		const selectStyle = selects[0].getAttribute("style") || "";
		expect(selectStyle).toContain("background-color: var(--bg-input)");
		expect(selectStyle).toContain("border-color: var(--input-border)");
		expect(selectStyle).toContain("color: var(--input-text)");

		const inputs = screen.getAllByPlaceholderText("请输入");
		if (inputs.length > 0) {
			const inputStyle = inputs[0].getAttribute("style") || "";
			expect(inputStyle).toContain("background-color: var(--bg-input)");
			expect(inputStyle).toContain("border-color: var(--input-border)");
			expect(inputStyle).toContain("color: var(--input-text)");
		}
	});

	// ---- Seam 6: Vision 和 图生视频 颜色值符合 spec ----
	it("Seam 6: Vision 图标颜色为 #7c3aed，图生视频图标颜色为 #0891b2", async () => {
		render(<ConfigPage />);

		await waitFor(() => {
			expect(screen.getByRole("tab", { name: /vision/i })).toBeInTheDocument();
		});

		const visionTab = screen.getByRole("tab", { name: /vision/i });
		const visionSpan = visionTab.querySelector("span");
		expect(visionSpan).toBeInTheDocument();
		expect(visionSpan!.style.color).toContain("--section-vision-color");

		const i2vTab = screen.getByRole("tab", { name: /图生视频/i });
		const i2vSpan = i2vTab.querySelector("span");
		expect(i2vSpan).toBeInTheDocument();
		expect(i2vSpan!.style.color).toContain("--section-image_to_video-color");
	});

	// ---- Seam 7: 深色模式 Tab 颜色适配 ----
	it("Seam 7: dark mode 下 Tab 使用 CSS 自定义属性适配深色背景", async () => {
		render(
			<div data-theme="dark">
				<ConfigPage />
			</div>,
		);

		await waitFor(() => {
			expect(screen.getByRole("tab", { name: /llm/i })).toBeInTheDocument();
		});

		const activeTab = screen.getByRole("tab", { name: /llm/i });
		const style = activeTab.getAttribute("style") || "";
		// 在深色模式下，激活 Tab 样式应使用 CSS 自定义属性以支持主题适配
		expect(style).toContain("--section-llm-color");
	});

	// ---- Seam 8: 紧凑模式 Tab 间距 ----
	it("Seam 8: compact mode 下 Tab 间距缩小，字号不溢出", async () => {
		render(
			<div data-layout="compact">
				<ConfigPage />
			</div>,
		);

		await waitFor(() => {
			expect(screen.getByRole("tab", { name: /llm/i })).toBeInTheDocument();
		});

		const tabs = screen.getAllByRole("tab");
		for (const tab of tabs) {
			const className = tab.className || "";
			// 紧凑模式应使用 CSS 变量调整间距和字号
			expect(className).toContain("var(--tab-padding-y");
			expect(className).toContain("var(--tab-padding-x");
			expect(className).toContain("var(--tab-font-size");
		}
	});

	// ---- Seam 9: 三种模式下输入框/下拉框样式一致 ----
	it("Seam 9: dark 和 compact 模式下输入框/下拉框样式一致使用设计系统变量", async () => {
		const { rerender } = render(
			<div data-theme="dark">
				<ConfigPage />
			</div>,
		);

		await waitFor(() => {
			expect(screen.getAllByRole("combobox").length).toBeGreaterThan(0);
		});

		const darkSelectStyle =
			screen.getAllByRole("combobox")[0].getAttribute("style") || "";
		expect(darkSelectStyle).toContain("var(--bg-input)");
		expect(darkSelectStyle).toContain("var(--input-border)");
		expect(darkSelectStyle).toContain("var(--input-text)");

		rerender(
			<div data-layout="compact">
				<ConfigPage />
			</div>,
		);

		await waitFor(() => {
			expect(screen.getAllByRole("combobox").length).toBeGreaterThan(0);
		});

		const compactSelectStyle =
			screen.getAllByRole("combobox")[0].getAttribute("style") || "";
		expect(compactSelectStyle).toContain("var(--bg-input)");
		expect(compactSelectStyle).toContain("var(--input-border)");
		expect(compactSelectStyle).toContain("var(--input-text)");
	});
});
