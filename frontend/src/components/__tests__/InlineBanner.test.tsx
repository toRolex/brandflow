import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import InlineBanner from "../InlineBanner";

describe("InlineBanner", () => {
  it("renders success message with correct styling", () => {
    render(
      <InlineBanner type="success" message="操作成功" onClose={vi.fn()} />,
    );
    expect(screen.getByText("操作成功")).toBeInTheDocument();
    const banner = screen.getByRole("alert");
    expect(banner.className).toContain("success");
  });

  it("renders error message with correct styling", () => {
    render(
      <InlineBanner type="error" message="操作失败" onClose={vi.fn()} />,
    );
    expect(screen.getByText("操作失败")).toBeInTheDocument();
    const banner = screen.getByRole("alert");
    expect(banner.className).toContain("danger");
  });

  it("calls onClose when close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <InlineBanner type="success" message="测试" onClose={onClose} />,
    );
    fireEvent.click(screen.getByLabelText("关闭"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("auto-hides success after default 3 seconds", () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onClose = vi.fn();
    render(
      <InlineBanner type="success" message="自动消失" onClose={onClose} />,
    );
    expect(screen.getByText("自动消失")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("自动消失")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it("does not auto-hide error by default", () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onClose = vi.fn();
    render(
      <InlineBanner type="error" message="错误信息" onClose={onClose} />,
    );
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText("错误信息")).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("respects custom autoHideMs", () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onClose = vi.fn();
    render(
      <InlineBanner
        type="error"
        message="自定义时间"
        onClose={onClose}
        autoHideMs={1000}
      />,
    );
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(onClose).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("hides banner when autoHideMs is 0", () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onClose = vi.fn();
    render(
      <InlineBanner
        type="success"
        message="不自动消失"
        onClose={onClose}
        autoHideMs={0}
      />,
    );
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(onClose).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});
