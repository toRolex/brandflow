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
			artifacts: [
				{
					kind: "selected_clips",
					relative_path: "clips.json",
					url: "/clips.json",
				},
			],
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
				error: {
					code: "ASSET_SEARCH_TIMEOUT",
					message: "Timed out",
					retryable: true,
				},
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

	it.each([
		["pending", "waiting"],
		["running", "running"],
		["retrying", "retrying"],
		["failed", "recoverable_error"],
		["succeeded", "completed"],
	] as const)("presents execution state %s as %s", (executionStatus, kind) => {
		const status = presentPhaseStatus({
			...base,
			phase: "scene_assembling",
			execution: {
				status: executionStatus,
				current_attempt: 2,
				max_attempts: 3,
				error:
					executionStatus === "retrying" || executionStatus === "failed"
						? {
								code: "TRANSIENT",
								message: "Temporary failure",
								retryable: true,
							}
						: null,
			},
		});

		expect(status.kind).toBe(kind);
	});

	it.each([
		["script_review", "script"],
		["tts_review", "tts_audio"],
		["subtitle_generating", "subtitle"],
		["asset_review", "selected_clips"],
		["video_rendering", "video_base"],
		["final_review", "final_video"],
		["completed", "final_video"],
	] as const)(
		"requires %s output before presenting %s as complete",
		(phase, artifact) => {
			const status = presentPhaseStatus({
				...base,
				phase,
				execution: { ...base.execution, status: "succeeded" },
			});

			expect(status.kind).toBe("integrity_error");
			expect(status.detail).toContain(artifact);
		},
	);
});
