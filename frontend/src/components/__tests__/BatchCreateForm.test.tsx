import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import BatchCreateForm from "../BatchCreateForm";

vi.mock("../../api/client", () => ({
	api: {
		getSceneFolders: vi.fn(() => Promise.resolve({ folders: [] })),
	},
}));

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

	it("generate 模式下批量提交也保留 manual_script", async () => {
		const onBatchCreate = vi.fn().mockResolvedValue(undefined);
		render(<BatchCreateForm {...defaultProps({ onBatchCreate })} />);

		const productInput = screen.getByPlaceholderText("如：龙井茶");
		fireEvent.change(productInput, { target: { value: "测试产品" } });

		uploadTextFile("第一段文案。\n\n第二段文案。");

		await waitFor(() => {
			expect(
				screen.getAllByPlaceholderText("请输入文案内容（150-200字）..."),
			).toHaveLength(2);
		});

		const submitBtn = screen.getByText(/批量创建 2 个 Job/);
		fireEvent.click(submitBtn);

		await waitFor(() => {
			expect(onBatchCreate).toHaveBeenCalledTimes(1);
		});

		const payload = onBatchCreate.mock.calls[0][0];
		expect(payload.jobs).toHaveLength(2);
		expect(payload.jobs[0].productionMode).toBe("generate");
		expect(payload.jobs[0].manualScript).toBe("第一段文案。");
		expect(payload.jobs[1].manualScript).toBe("第二段文案。");
	});

	it("import 模式下批量提交携带选中的场景文件夹", async () => {
		vi.mocked(api.getSceneFolders).mockResolvedValue({
			folders: [{ name: "场景一", path: "scenes/one" }],
		});
		const onBatchCreate = vi.fn().mockResolvedValue(undefined);
		render(
			<BatchCreateForm
				{...defaultProps({ onBatchCreate, product: "测试产品" })}
			/>,
		);

		await waitFor(() => {
			expect(screen.getByLabelText("场景一")).toBeInTheDocument();
		});
		fireEvent.click(screen.getByLabelText("场景一"));

		const submitBtn = screen.getByText(/批量创建 2 个 Job/);
		fireEvent.click(submitBtn);

		await waitFor(() => {
			expect(onBatchCreate).toHaveBeenCalledTimes(1);
		});

		const payload = onBatchCreate.mock.calls[0][0];
		expect(payload.jobs[0].sceneFolderIds).toEqual(["scenes/one"]);
		expect(payload.jobs[1].sceneFolderIds).toEqual(["scenes/one"]);
	});

	it("generate 模式下不加载场景文件夹且不显示错误", async () => {
		vi.mocked(api.getSceneFolders).mockRejectedValue(new Error("should not be called"));
		const onError = vi.fn();
		render(
			<BatchCreateForm
				{...defaultProps({ onError, product: "测试产品" })}
			/>,
		);

		await waitFor(() => {
			expect(screen.getByText("未配置场景文件夹")).toBeInTheDocument();
		});
		expect(api.getSceneFolders).not.toHaveBeenCalled();
		expect(onError).not.toHaveBeenCalled();
	});

	it("存在 import 任务时才加载场景文件夹", async () => {
		vi.mocked(api.getSceneFolders).mockResolvedValue({
			folders: [{ name: "场景一", path: "scenes/one" }],
		});
		render(<BatchCreateForm {...defaultProps({ product: "测试产品" })} />);

		// 默认全部为 generate，不应调用
		await waitFor(() => {
			expect(screen.getByText("未配置场景文件夹")).toBeInTheDocument();
		});
		expect(api.getSceneFolders).not.toHaveBeenCalled();

		// 切换第一个任务为 import
		fireEvent.click(screen.getAllByText("手动导入")[0]);

		await waitFor(() => {
			expect(screen.getByLabelText("场景一")).toBeInTheDocument();
		});
		expect(api.getSceneFolders).toHaveBeenCalledWith("测试产品");
	});
});
