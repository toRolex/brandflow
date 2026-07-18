import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import QualityRulesForm from "../QualityRulesForm";

vi.mock("../../api/client", () => ({
	api: {
		getProductConfig: vi.fn(),
		saveProductConfig: vi.fn(),
		resetProductConfig: vi.fn(),
	},
}));

const MOCK_CONFIG = {
	default_name: "示例产品",
	default_brand: "示例品牌",
	script: {
		scene: "产品展示、制作过程、成品呈现",
		material: "产品近景、细节处理、使用场景",
		system_prompt: "你是一位美食短视频文案专家。",
		word_count_min: 150,
		word_count_max: 200,
		forbidden_words: ["治疗", "治愈", "疗效", "降血糖"],
		emoji_forbidden: true,
		product_name_count: 1,
		brand_name_count: 1,
	},
};

describe("QualityRulesForm", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(api.getProductConfig).mockResolvedValue(MOCK_CONFIG);
	});

	it("加载时调用 API 并展示质检规则", async () => {
		render(<QualityRulesForm />);
		expect(api.getProductConfig).toHaveBeenCalledTimes(1);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});
		expect(screen.getByDisplayValue("200")).toBeInTheDocument();
		expect(screen.getAllByDisplayValue("1")).toHaveLength(2); // product_name_count + brand_name_count
		expect(screen.getByText("治疗")).toBeInTheDocument();
		expect(screen.getByText("治愈")).toBeInTheDocument();
		expect(screen.getByText("疗效")).toBeInTheDocument();
		expect(screen.getByText("降血糖")).toBeInTheDocument();
	});

	it("加载失败时显示错误提示", async () => {
		vi.mocked(api.getProductConfig).mockRejectedValue(
			new Error("Network Error"),
		);
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByText("加载质检规则失败")).toBeInTheDocument();
		});
	});

	it("修改字数范围后显示提示信息", async () => {
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		const minInput = screen.getByDisplayValue("150");
		fireEvent.change(minInput, { target: { value: "100" } });

		const maxInput = screen.getByDisplayValue("200");
		fireEvent.change(maxInput, { target: { value: "250" } });

		await waitFor(() => {
			expect(screen.getByText("字数必须在 100-250 之间")).toBeInTheDocument();
		});
	});

	it("字数范围无效时显示红色验证提示", async () => {
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		const minInput = screen.getByDisplayValue("150");
		fireEvent.change(minInput, { target: { value: "300" } });

		const maxInput = screen.getByDisplayValue("200");
		fireEvent.change(maxInput, { target: { value: "100" } });

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			// The error appears both in the save message and the inline validation
			expect(
				screen.getAllByText("最小值不能大于最大值").length,
			).toBeGreaterThanOrEqual(1);
		});
	});

	it("保存按钮调用 PUT API", async () => {
		vi.mocked(api.saveProductConfig).mockResolvedValue(MOCK_CONFIG);
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		const saveBtn = screen.getByText("保存配置");
		fireEvent.click(saveBtn);

		await waitFor(() => {
			expect(api.saveProductConfig).toHaveBeenCalledTimes(1);
		});
	});

	it("保存成功后显示成功提示", async () => {
		vi.mocked(api.saveProductConfig).mockResolvedValue(MOCK_CONFIG);
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		fireEvent.click(screen.getByText("保存配置"));

		await waitFor(() => {
			expect(screen.getByText("配置已保存")).toBeInTheDocument();
		});
	});

	it("保存失败时显示错误提示", async () => {
		vi.mocked(api.saveProductConfig).mockRejectedValue(
			new Error("Save failed"),
		);
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		fireEvent.click(screen.getByText("保存配置"));

		await waitFor(() => {
			expect(screen.getByText("保存失败")).toBeInTheDocument();
		});
	});

	it("恢复默认按钮调用 DELETE API", async () => {
		vi.mocked(api.resetProductConfig).mockResolvedValue({ status: "ok" });
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		const resetBtn = screen.getByText("恢复默认");
		fireEvent.click(resetBtn);

		await waitFor(() => {
			expect(api.resetProductConfig).toHaveBeenCalledTimes(1);
		});
	});

	it("新增禁词", async () => {
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		const addBtn = screen.getByText("+ 添加");
		fireEvent.click(addBtn);

		await waitFor(() => {
			expect(screen.getByPlaceholderText("输入禁词")).toBeInTheDocument();
		});

		const input = screen.getByPlaceholderText("输入禁词");
		fireEvent.change(input, { target: { value: "保证" } });

		const confirmBtn = screen.getByText("确认");
		fireEvent.click(confirmBtn);

		await waitFor(() => {
			expect(screen.getByText("保证")).toBeInTheDocument();
		});
	});

	it("删除禁词", async () => {
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByText("治疗")).toBeInTheDocument();
		});

		// Find and click the delete button on the "治疗" chip
		const chipCloseButtons = screen.getAllByText("×");
		fireEvent.click(chipCloseButtons[0]);

		await waitFor(() => {
			expect(screen.queryByText("治疗")).not.toBeInTheDocument();
		});
	});

	it("emoji 开关切换", async () => {
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		const toggle = screen.getByRole("checkbox");
		expect(toggle).toBeChecked();

		fireEvent.click(toggle);

		expect(toggle).not.toBeChecked();
	});

	it("新增禁词时必填验证", async () => {
		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		const addBtn = screen.getByText("+ 添加");
		fireEvent.click(addBtn);

		await waitFor(() => {
			expect(screen.getByPlaceholderText("输入禁词")).toBeInTheDocument();
		});

		const confirmBtn = screen.getByText("确认");
		fireEvent.click(confirmBtn);

		await waitFor(() => {
			expect(screen.getByText("禁词不能为空")).toBeInTheDocument();
		});
	});

	it("页面标题正确显示", async () => {
		render(<QualityRulesForm />);
		await waitFor(() => {
			expect(screen.getByText("质检规则")).toBeInTheDocument();
		});
	});

	it("恢复默认后重新加载配置", async () => {
		vi.mocked(api.resetProductConfig).mockResolvedValue({ status: "ok" });
		vi.mocked(api.getProductConfig).mockReset();
		vi.mocked(api.getProductConfig).mockResolvedValueOnce(MOCK_CONFIG);
		vi.mocked(api.getProductConfig).mockResolvedValueOnce(MOCK_CONFIG);

		render(<QualityRulesForm />);

		await waitFor(() => {
			expect(screen.getByDisplayValue("150")).toBeInTheDocument();
		});

		fireEvent.click(screen.getByText("恢复默认"));

		await waitFor(() => {
			expect(api.getProductConfig).toHaveBeenCalledTimes(2);
		});
	});
});
