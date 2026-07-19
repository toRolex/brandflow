import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BatchScriptUploader from "./BatchScriptUploader";

describe("BatchScriptUploader", () => {
	it("解析 .txt 文件并按空行拆分文案", async () => {
		const onScripts = vi.fn();
		render(<BatchScriptUploader onScripts={onScripts} />);

		const file = new File(["第一段文案。\n\n第二段文案。"], "scripts.txt", {
			type: "text/plain",
		});
		const input = screen.getByLabelText("上传文案文件");
		fireEvent.change(input, { target: { files: [file] } });

		await waitFor(() => {
			expect(onScripts).toHaveBeenCalledWith(["第一段文案。", "第二段文案。"]);
		});
	});

	it("过滤空片段与首尾空白", async () => {
		const onScripts = vi.fn();
		render(<BatchScriptUploader onScripts={onScripts} />);

		const file = new File(
			["\n\n  第一段文案。  \n\n\n\n  第二段文案。  \n\n"],
			"scripts.txt",
			{ type: "text/plain" },
		);
		const input = screen.getByLabelText("上传文案文件");
		fireEvent.change(input, { target: { files: [file] } });

		await waitFor(() => {
			expect(onScripts).toHaveBeenCalledWith(["第一段文案。", "第二段文案。"]);
		});
	});

	it("兼容 Windows 换行符", async () => {
		const onScripts = vi.fn();
		render(<BatchScriptUploader onScripts={onScripts} />);

		const file = new File(["第一段文案。\r\n\r\n第二段文案。"], "scripts.txt", {
			type: "text/plain",
		});
		const input = screen.getByLabelText("上传文案文件");
		fireEvent.change(input, { target: { files: [file] } });

		await waitFor(() => {
			expect(onScripts).toHaveBeenCalledWith(["第一段文案。", "第二段文案。"]);
		});
	});

	it("当未选择文件时不触发回调", () => {
		const onScripts = vi.fn();
		render(<BatchScriptUploader onScripts={onScripts} />);

		const input = screen.getByLabelText("上传文案文件");
		fireEvent.change(input, { target: { files: [] } });

		expect(onScripts).not.toHaveBeenCalled();
	});
});
