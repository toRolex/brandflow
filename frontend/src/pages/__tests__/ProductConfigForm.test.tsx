import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ProductConfigForm from "../ProductConfigForm";
import { api } from "../../api/client";

vi.mock("../../api/client", () => ({
  api: {
    getProductConfig: vi.fn(),
    saveProductConfig: vi.fn(),
    resetProductConfig: vi.fn(),
  },
}));

const MOCK_CONFIG = {
  default_name: "羊肚菌",
  default_brand: "菌王山珍",
  script: {
    scene: "食材展示、烹饪过程、成品呈现",
    material: "食材近景、清洗处理、烹饪翻炒",
    system_prompt: "你是一位美食短视频文案专家。",
  },
};

describe("ProductConfigForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getProductConfig).mockResolvedValue(MOCK_CONFIG);
  });

  it("加载时调用 API 并回显配置", async () => {
    render(<ProductConfigForm />);
    expect(api.getProductConfig).toHaveBeenCalledTimes(1);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue("菌王山珍")).toBeInTheDocument();
    expect(screen.getByDisplayValue("食材展示、烹饪过程、成品呈现")).toBeInTheDocument();
    expect(screen.getByDisplayValue("食材近景、清洗处理、烹饪翻炒")).toBeInTheDocument();
    expect(screen.getByDisplayValue("你是一位美食短视频文案专家。")).toBeInTheDocument();
  });

  it("加载失败时显示错误提示", async () => {
    vi.mocked(api.getProductConfig).mockRejectedValue(new Error("Network Error"));
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByText("加载产品配置失败")).toBeInTheDocument();
    });
  });

  it("保存按钮调用 PUT API", async () => {
    vi.mocked(api.saveProductConfig).mockResolvedValue(MOCK_CONFIG);
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const saveBtn = screen.getByText("保存配置");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
      expect(api.saveProductConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          default_name: "羊肚菌",
          default_brand: "菌王山珍",
        })
      );
    });
  });

  it("保存成功后显示成功提示", async () => {
    vi.mocked(api.saveProductConfig).mockResolvedValue(MOCK_CONFIG);
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const saveBtn = screen.getByText("保存配置");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("配置已保存")).toBeInTheDocument();
    });
  });

  it("保存失败时显示错误提示", async () => {
    vi.mocked(api.saveProductConfig).mockRejectedValue(new Error("Save failed"));
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const saveBtn = screen.getByText("保存配置");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("保存失败")).toBeInTheDocument();
    });
  });

  it("重置按钮调用 DELETE API", async () => {
    vi.mocked(api.resetProductConfig).mockResolvedValue({ status: "ok" });
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const resetBtn = screen.getByText("重置为默认值");
    fireEvent.click(resetBtn);

    await waitFor(() => {
      expect(api.resetProductConfig).toHaveBeenCalledTimes(1);
    });
  });

  it("重置后重新加载配置", async () => {
    const defaultConfig = {
      default_name: "",
      default_brand: "",
      script: {
        scene: "默认场景描述",
        material: "默认素材描述",
        system_prompt: "默认系统提示词",
      },
    };
    vi.mocked(api.resetProductConfig).mockResolvedValue({ status: "ok" });
    // First call returns MOCK_CONFIG, reload after reset returns default
    vi.mocked(api.getProductConfig).mockReset();
    vi.mocked(api.getProductConfig).mockResolvedValueOnce(MOCK_CONFIG);
    vi.mocked(api.getProductConfig).mockResolvedValueOnce(defaultConfig);

    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const resetBtn = screen.getByText("重置为默认值");
    fireEvent.click(resetBtn);

    await waitFor(() => {
      expect(api.getProductConfig).toHaveBeenCalledTimes(2);
    });
  });

  it("修改字段值后输入框反映新值", async () => {
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const nameInput = screen.getByDisplayValue("羊肚菌");
    fireEvent.change(nameInput, { target: { value: "松茸" } });

    expect(screen.getByDisplayValue("松茸")).toBeInTheDocument();
  });

  it("表单验证：产品名为空时显示错误", async () => {
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const nameInput = screen.getByDisplayValue("羊肚菌");
    fireEvent.change(nameInput, { target: { value: "" } });

    const saveBtn = screen.getByText("保存配置");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("产品名不能为空")).toBeInTheDocument();
    });

    // API should NOT be called when validation fails
    expect(api.saveProductConfig).not.toHaveBeenCalled();
  });

  it("表单验证：品牌名为空时显示错误", async () => {
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const brandInput = screen.getByDisplayValue("菌王山珍");
    fireEvent.change(brandInput, { target: { value: "" } });

    const saveBtn = screen.getByText("保存配置");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("品牌名不能为空")).toBeInTheDocument();
    });

    expect(api.saveProductConfig).not.toHaveBeenCalled();
  });

  it("表单验证：产品名字数超过限制时显示错误", async () => {
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const nameInput = screen.getByDisplayValue("羊肚菌");
    fireEvent.change(nameInput, { target: { value: "a".repeat(51) } });

    const saveBtn = screen.getByText("保存配置");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("产品名不能超过50字")).toBeInTheDocument();
    });

    expect(api.saveProductConfig).not.toHaveBeenCalled();
  });

  it("表单验证：品牌名字数超过限制时显示错误", async () => {
    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const brandInput = screen.getByDisplayValue("菌王山珍");
    fireEvent.change(brandInput, { target: { value: "a".repeat(51) } });

    const saveBtn = screen.getByText("保存配置");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("品牌名不能超过50字")).toBeInTheDocument();
    });

    expect(api.saveProductConfig).not.toHaveBeenCalled();
  });

  it("保存时显示保存中状态", async () => {
    // Return a promise that never resolves during the test
    vi.mocked(api.saveProductConfig).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(MOCK_CONFIG), 1000))
    );

    render(<ProductConfigForm />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("羊肚菌")).toBeInTheDocument();
    });

    const saveBtn = screen.getByText("保存配置");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("保存中...")).toBeInTheDocument();
    });
  });

  it("页面标题正确显示", async () => {
    render(<ProductConfigForm />);
    await waitFor(() => {
      expect(screen.getByText("产品配置")).toBeInTheDocument();
    });
  });
});
