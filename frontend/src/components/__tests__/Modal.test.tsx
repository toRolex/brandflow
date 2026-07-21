import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Modal from "../Modal";

describe("Modal", () => {
  it("renders children when isOpen is true", () => {
    render(
      <Modal isOpen={true} title="测试弹窗" onClose={vi.fn()}>
        <p>弹窗内容</p>
      </Modal>,
    );
    expect(screen.getByText("弹窗内容")).toBeInTheDocument();
    expect(screen.getByText("测试弹窗")).toBeInTheDocument();
  });

  it("uses a responsive, scrollable wide layout when requested", () => {
    const { container } = render(
      <Modal isOpen={true} title="宽版弹窗" onClose={vi.fn()} size="wide">
        <p>很长的内容</p>
      </Modal>,
    );

    const panel = container.querySelector(".max-w-5xl");
    const content = container.querySelector(".overflow-y-auto.overscroll-contain");

    expect(panel).toHaveClass("w-full", "max-h-full");
    expect(content).toBeInTheDocument();
  });

  it("does not render when isOpen is false", () => {
    render(
      <Modal isOpen={false} title="测试弹窗" onClose={vi.fn()}>
        <p>弹窗内容</p>
      </Modal>,
    );
    expect(screen.queryByText("弹窗内容")).not.toBeInTheDocument();
  });

  it("calls onClose when Escape is pressed", () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen={true} title="测试弹窗" onClose={onClose}>
        <p>内容</p>
      </Modal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when backdrop is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal isOpen={true} title="测试弹窗" onClose={onClose}>
        <p>内容</p>
      </Modal>,
    );
    // The backdrop is the first child div with absolute inset-0
    const backdrop = container.querySelector(
      ".absolute.inset-0",
    ) as HTMLElement;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen={true} title="测试弹窗" onClose={onClose}>
        <p>内容</p>
      </Modal>,
    );
    fireEvent.click(screen.getByLabelText("关闭"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not listen to Escape when closed", () => {
    const onClose = vi.fn();
    render(
      <Modal isOpen={false} title="测试弹窗" onClose={onClose}>
        <p>内容</p>
      </Modal>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
