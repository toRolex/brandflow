import { describe, expect, it } from "vitest";
import { presentPhaseStatus } from "./phasePresentation";

describe("presentPhaseStatus", () => {
	const base = {
		phase: "asset_retrieving" as const,
		execution: {
			status: "succeeded" as const,
			current_attempt: 1,
			max_attempts: 3,
			error: null,
		},
		reviewStatus: "none" as const,
		artifacts: [],
	};

	it("distinguishes a successful zero-match search from a missing search result", () => {
		const zeroMatch = presentPhaseStatus({
			...base,
			artifacts: [{ kind: "selected_clips", relative_path: "clips.json", url: "/clips.json" }],
			assetDecisions: { total: 3, clip: 0, unresolved: 3, blank: 0 },
		});
		const missingResult = presentPhaseStatus({ ...base });

		expect(zeroMatch.kind).toBe("needs_business_decision");
		expect(zeroMatch.action).toBe("review_assets");
		expect(missingResult.kind).toBe("integrity_error");
		expect(missingResult.action).toBe("view_logs");
	});

	it("preserves retrying as an execution state with the last error", () => {
		const status = presentPhaseStatus({
			...base,
			execution: {
				status: "retrying",
				current_attempt: 2,
				max_attempts: 3,
				error: { code: "ASSET_SEARCH_TIMEOUT", message: "Timed out", retryable: true },
			},
		});

		expect(status.kind).toBe("retrying");
		expect(status.detail).toContain("Timed out");
		expect(status.action).toBe("wait_for_retry");
	});

	it("does not call a completed job complete without its final video", () => {
		const status = presentPhaseStatus({
			...base,
			phase: "completed",
			execution: { ...base.execution, status: "succeeded" },
			requiredArtifacts: ["final_video"],
		});

		expect(status.kind).toBe("integrity_error");
	});
});
