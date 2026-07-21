import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import InlineBanner from "../InlineBanner";

describe("InlineBanner", () => {
	it("renders success message", () => {
		render(<InlineBanner type="success" message="操作成功" onClose={vi.fn()} />);
		expect(screen.getByText("操作成功")).toBeInTheDocument();
	});

	it("renders error message", () => {
		render(<InlineBanner type="error" message="操作失败" />);
		expect(screen.getByText("操作失败")).toBeInTheDocument();
	});

	it("calls onClose when close button is clicked", () => {
		const onClose = vi.fn();
		render(<InlineBanner type="success" message="操作成功" onClose={onClose} />);
		fireEvent.click(screen.getByLabelText("关闭"));
		expect(onClose).toHaveBeenCalledTimes(1);
	});
});
