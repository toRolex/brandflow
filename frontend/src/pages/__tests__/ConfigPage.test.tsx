import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ConfigPage from "../ConfigPage";
import { api } from "../../api/client";

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
        deepseek: { label: "DeepSeek", fields: [{ name: "model", label: "模型", kind: "select", options: ["deepseek-v4-pro"] }, { name: "api_key", label: "API Key", kind: "text", secret: true }] },
        kimi: { label: "Kimi", fields: [{ name: "model", label: "模型", kind: "text" }] },
      },
    },
    tts: {
      providers: {
        qwen: { label: "通义千问", fields: [{ name: "voice", label: "音色", kind: "text" }] },
        mimo: { label: "MiMo", fields: [{ name: "model", label: "模型", kind: "text" }] },
      },
    },
    vision: {
      providers: {
        xiaomi: { label: "小米", fields: [{ name: "model", label: "模型", kind: "text" }] },
        claude: { label: "Claude", fields: [{ name: "model", label: "模型", kind: "text" }] },
      },
    },
    text_to_image: {
      providers: {
        dalle: { label: "DALL-E", fields: [{ name: "model", label: "模型", kind: "text" }] },
        midjourney: { label: "Midjourney", fields: [{ name: "model", label: "模型", kind: "text" }] },
      },
    },
    image_to_video: {
      providers: {
        runway: { label: "Runway", fields: [{ name: "model", label: "模型", kind: "text" }] },
        pika: { label: "Pika", fields: [{ name: "model", label: "模型", kind: "text" }] },
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

  it("Seam 1: 5 个 section 以横向 Tab 渲染，默认选中 LLM", async () => {
    render(<ConfigPage />);

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /llm/i })).toBeInTheDocument();
    });

    expect(screen.getByRole("tab", { name: /tts/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /vision/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /文生图/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /图生视频/i })).toBeInTheDocument();

    expect(screen.getByRole("tab", { name: /llm/i })).toHaveAttribute("aria-selected", "true");
  });

  it("Seam 1: 切换 Tab 显示对应 section 的 provider 选择", async () => {
    render(<ConfigPage />);

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /llm/i })).toBeInTheDocument();
    });

    expect(screen.getByText("DeepSeek")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /tts/i }));
    expect(screen.getByText("通义千问")).toBeInTheDocument();

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

    const tabs = ["llm", "tts", "vision", "text_to_image", "image_to_video"];
    const expectedColors = {
      llm: "#3b82f6",
      tts: "#22c55e",
      vision: "#a855f7",
      text_to_image: "#f59e0b",
      image_to_video: "#06b6d4",
    };

    for (const key of tabs) {
      const tab = screen.getByRole("tab", { name: new RegExp(key === "text_to_image" ? "文生图" : key === "image_to_video" ? "图生视频" : key, "i") });
      const icon = tab.querySelector("svg");
      expect(icon).toBeInTheDocument();
      // Tab icons use the configured color via fill or stroke
      const color = expectedColors[key as keyof typeof expectedColors];
      expect(icon?.innerHTML.includes(color) || icon?.getAttribute("fill") === color || icon?.getAttribute("stroke") === color || icon?.style.color === color).toBeTruthy();
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

    // Save button should be in header row area
    const header = screen.getByText("系统配置").parentElement;
    expect(header?.contains(saveBtn)).toBe(true);

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
      expect(screen.getByRole("button", { name: /保存配置/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /保存配置/i }));

    await waitFor(() => {
      expect(screen.getByText(/保存失败/i)).toBeInTheDocument();
    });
  });

  it("Seam 4: 页面加载时自动选中每个 section 的第一个 provider", async () => {
    render(<ConfigPage />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("deepseek-v4-pro")).toBeInTheDocument();
    });

    // LLM first provider is deepseek, model field is shown
    expect(screen.getByDisplayValue("deepseek-v4-pro")).toBeInTheDocument();

    // Switch to TTS and verify first provider selected (voice field appears)
    fireEvent.click(screen.getByRole("tab", { name: /tts/i }));
    expect(screen.getByText("音色")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveValue("qwen");
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
});
