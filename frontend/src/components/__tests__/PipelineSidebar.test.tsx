import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PipelineSidebar from "../PipelineSidebar";

const defaultProps = {
	completedPhases: [],
	onStepClick: vi.fn(),
	activeStepKey: "",
	actionPolicy: {
		canPause: true,
		canResume: false,
		canCancel: true,
		canRetry: false,
		pauseMessage: null,
		retryMessage: "仅失败的 Job 可以重新执行失败阶段。",
	},
};

describe("PipelineSidebar mode-specific phases (#262 follow-up)", () => {
	it("shows only phases that a generate job can execute", () => {
		render(
			<PipelineSidebar
				{...defaultProps}
				currentPhase="script_generating"
				activeStepKey="script_gen"
				mode="generate"
			/>,
		);

		const scriptStep = screen.getByRole("button", { name: /生成脚本/ });
		expect(scriptStep).toHaveAttribute("aria-current", "step");
		const scriptReviewStep = screen.getByRole("button", { name: /脚本审核/ });
		expect(within(scriptReviewStep).getByText("4")).toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: /场景拼接/ }),
		).not.toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: /需补充场景/ }),
		).not.toBeInTheDocument();
	});

	it("shows only phases that an import job can execute", () => {
		render(
			<PipelineSidebar
				{...defaultProps}
				currentPhase="subtitle_generating"
				activeStepKey="subtitle"
				mode="import"
			/>,
		);

		expect(
			screen.getByRole("button", { name: /场景拼接/ }),
		).toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: /生成脚本/ }),
		).not.toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: /脚本审核/ }),
		).not.toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: /TTS 审核/ }),
		).not.toBeInTheDocument();
		expect(
			screen.queryByRole("button", { name: /需补充场景/ }),
		).not.toBeInTheDocument();
	});

	it("shows migration guidance only while migration is required", () => {
		render(
			<PipelineSidebar
				{...defaultProps}
				currentPhase="migration_required"
				activeStepKey="migration_required"
				mode="import"
			/>,
		);

		expect(screen.getByRole("button", { name: /需补充场景/ })).toHaveAttribute(
			"aria-current",
			"step",
		);
	});
});
