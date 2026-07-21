import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ConfirmDialog from "../ConfirmDialog";

describe("ConfirmDialog", () => {
	it("calls onConfirm when confirm button is clicked", () => {
		const onConfirm = vi.fn();
		const onCancel = vi.fn();
		render(
			<ConfirmDialog
				isOpen
				title="确认"
				message="确定吗？"
				onConfirm={onConfirm}
				onCancel={onCancel}
				confirmLabel="确认删除"
				danger
			/>,
		);

		fireEvent.click(screen.getByText("确认删除"));
		expect(onConfirm).toHaveBeenCalledTimes(1);
		expect(onCancel).not.toHaveBeenCalled();
	});
});
