import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BatchCreateForm from "../BatchCreateForm";

const defaultProps = (overrides: Record<string, unknown> = {}) => ({
	platforms: [] as string[],
	togglePlatform: vi.fn(),
	musicTracks: [],
	onBatchCreate: vi.fn().mockResolvedValue(undefined),
	onError: vi.fn(),
	...overrides,
});

function uploadTextFile(text: string) {
	const file = new File([text], "scripts.txt", { type: "text/plain" });
	const input = screen.getByLabelText("上传文案文件");
	fireEvent.change(input, { target: { files: [file] } });
}

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

	it("generate 模式下 scriptMode 为 manual 时渲染脚本输入框", async () => {
		render(<BatchCreateForm {...defaultProps()} />);
		uploadTextFile("第一段文案。\n\n第二段文案。");

		await waitFor(() => {
			expect(
				screen.getAllByPlaceholderText("请输入文案内容（150-200字）..."),
			).toHaveLength(2);
		});
	});

	it("generate 模式下 scriptMode 为 auto 时不渲染脚本输入框", () => {
		render(<BatchCreateForm {...defaultProps()} />);
		expect(
			screen.queryByPlaceholderText("请输入文案内容（150-200字）..."),
		).toBeNull();
	});

	it("切换生产模式时不重置 scriptMode", async () => {
		render(<BatchCreateForm {...defaultProps()} />);
		uploadTextFile("第一段文案。\n\n第二段文案。");

		await waitFor(() => {
			expect(
				screen.getAllByPlaceholderText("请输入文案内容（150-200字）..."),
			).toHaveLength(2);
		});

		// 切换到手动导入再切回智能生成
		fireEvent.click(screen.getAllByText("手动导入")[0]);
		fireEvent.click(screen.getAllByText("智能生成")[0]);

		await waitFor(() => {
			expect(
				screen.getAllByPlaceholderText("请输入文案内容（150-200字）..."),
			).toHaveLength(2);
		});
	});
});
