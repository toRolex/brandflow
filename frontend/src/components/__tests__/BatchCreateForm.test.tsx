import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import BatchCreateForm from "../BatchCreateForm";

const defaultProps = (overrides: Record<string, unknown> = {}) => ({
  product: "",
  setProduct: vi.fn(),
  brand: "",
  setBrand: vi.fn(),
  platforms: [] as string[],
  togglePlatform: vi.fn(),
  musicTracks: [],
  onBatchCreate: vi.fn().mockResolvedValue(undefined),
  onError: vi.fn(),
  ...overrides,
});

describe("BatchCreateForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should not render shared TTS config section", () => {
    render(<BatchCreateForm {...defaultProps()} />);
    expect(screen.queryByText("TTS 配置（所有任务共享）")).toBeNull();
  });

  it("should not have TTS model selector", () => {
    render(<BatchCreateForm {...defaultProps()} />);
    expect(screen.queryByLabelText("TTS 模型")).toBeNull();
  });

  it("should not have TTS voice selector", () => {
    render(<BatchCreateForm {...defaultProps()} />);
    expect(screen.queryByLabelText("TTS 音色")).toBeNull();
  });

  it("should call onBatchCreate without ttsModel/ttsVoice", async () => {
    const onBatchCreate = vi.fn().mockResolvedValue(undefined);
    render(<BatchCreateForm {...defaultProps({ onBatchCreate })} />);

    // Fill in required fields
    const productInput = screen.getByPlaceholderText("如：龙井茶");
    fireEvent.change(productInput, { target: { value: "测试产品" } });

    // Click submit
    const submitBtn = screen.getByText(/批量创建 2 个 Job/);
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(onBatchCreate).toHaveBeenCalledTimes(1);
    });

    const payload = onBatchCreate.mock.calls[0][0];
    expect(payload.ttsModel).toBeUndefined();
    expect(payload.ttsVoice).toBeUndefined();
  });
});
