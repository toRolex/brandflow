import { describe, expect, it } from "vitest";
import type { Artifact, Phase, PhaseExecutionState } from "../../types/core";
import { computePhasePresentation } from "../phasePresentation";

function exec(
	status: PhaseExecutionState["status"],
	overrides?: Partial<PhaseExecutionState>,
): PhaseExecutionState {
	return {
		status,
		current_attempt: 1,
		max_attempts: 3,
		error: null,
		...overrides,
	};
}

function artifact(kind: string): Artifact {
	return {
		kind,
		relative_path: `test/${kind}.json`,
		url: `/test/${kind}.json`,
	};
}

describe("computePhasePresentation", () => {
	describe("execution status priority", () => {
		it.each([
			[
				"failed retryable",
				{
					status: "failed",
					error: { code: "E1", message: "boom", retryable: true },
				},
				"failed",
				true,
				false,
			],
			[
				"failed non-retryable",
				{
					status: "failed",
					error: { code: "E2", message: "boom", retryable: false },
				},
				"failed",
				false,
				false,
			],
			[
				"retrying",
				{
					status: "retrying",
					error: { code: "E3", message: "retry", retryable: true },
					current_attempt: 2,
					max_attempts: 3,
				},
				"retrying",
				false,
				false,
			],
			[
				"running",
				{ status: "running", current_attempt: 1, max_attempts: 3 },
				"running",
				false,
				false,
			],
			["pending", { status: "pending" }, "pending", false, false],
		] as const)(
			"%s -> type=%s, showRetry=%s, showApproveReject=%s",
			(_label, execution, type, showRetry, showApproveReject) => {
				const p = computePhasePresentation({
					phase: "asset_retrieving",
					execution: exec(execution.status, execution),
					requiredArtifactKinds: ["selected_clips"],
					artifacts: [artifact("selected_clips")],
				});
				expect(p.type).toBe(type);
				expect(p.showRetry).toBe(showRetry);
				expect(p.showApproveReject).toBe(showApproveReject);
			},
		);

		it("failed takes priority over missing required artifact", () => {
			const p = computePhasePresentation({
				phase: "asset_retrieving",
				execution: exec("failed", {
					error: { code: "E", message: "failed", retryable: true },
				}),
				requiredArtifactKinds: ["selected_clips"],
				artifacts: [],
			});
			expect(p.type).toBe("failed");
			expect(p.title).toContain("失败");
		});

		it("retrying takes priority over missing required artifact", () => {
			const p = computePhasePresentation({
				phase: "asset_retrieving",
				execution: exec("retrying", {
					current_attempt: 2,
					error: { code: "E", message: "retry", retryable: true },
				}),
				requiredArtifactKinds: ["selected_clips"],
				artifacts: [],
			});
			expect(p.type).toBe("retrying");
			expect(p.message).toContain("正在自动重试");
			expect(p.message).toContain("2 / 3");
		});
	});

	describe("artifact completeness anomalies", () => {
		it("asset_retrieving succeeded without selected_clips is an anomaly", () => {
			const p = computePhasePresentation({
				phase: "asset_retrieving",
				execution: exec("succeeded"),
				requiredArtifactKinds: ["selected_clips"],
				artifacts: [],
			});
			expect(p.type).toBe("anomaly_missing_artifact");
			expect(p.title).toBe("素材检索结果异常");
			expect(p.showRetry).toBe(true);
			expect(p.isReadOnly).toBe(true);
		});

		it.each([
			["script_review", "script", "脚本审核输入缺失"],
			["tts_review", "tts_audio", "TTS 审核输入缺失"],
			["final_review", "final_video", "终审·烧录输入缺失"],
		] as const)(
			"%s succeeded without %s disables review actions",
			(phase, kind, titleContains) => {
				const p = computePhasePresentation({
					phase: phase as Phase,
					execution: exec("succeeded"),
					reviewStatus: "pending",
					requiredArtifactKinds: [kind],
					artifacts: [],
				});
				expect(p.type).toBe("anomaly_missing_artifact");
				expect(p.title).toContain(titleContains);
				expect(p.showApproveReject).toBe(false);
				expect(p.isReadOnly).toBe(true);
			},
		);

		it("completed without final_video is an incomplete record anomaly", () => {
			const p = computePhasePresentation({
				phase: "completed",
				execution: exec("succeeded"),
				requiredArtifactKinds: ["final_video"],
				artifacts: [],
			});
			expect(p.type).toBe("anomaly_missing_artifact");
			expect(p.title).toBe("完成记录不完整");
			expect(p.showRetry).toBe(false);
		});

		it("completed with final_video shows production complete", () => {
			const p = computePhasePresentation({
				phase: "completed",
				execution: exec("succeeded"),
				requiredArtifactKinds: ["final_video"],
				artifacts: [artifact("final_video")],
			});
			expect(p.type).toBe("completed");
			expect(p.title).toBe("生产完成");
		});
	});

	describe("review phases", () => {
		it("asset_review pending with selected_clips is review_ready", () => {
			const p = computePhasePresentation({
				phase: "asset_review",
				execution: exec("succeeded"),
				reviewStatus: "pending",
				requiredArtifactKinds: ["selected_clips"],
				artifacts: [artifact("selected_clips")],
			});
			expect(p.type).toBe("review_ready");
			expect(p.showApproveReject).toBe(true);
			expect(p.isReadOnly).toBe(false);
		});

		it("approved review phase is review_completed and read-only", () => {
			const p = computePhasePresentation({
				phase: "asset_review",
				execution: exec("succeeded"),
				reviewStatus: "approved",
				requiredArtifactKinds: ["selected_clips"],
				artifacts: [artifact("selected_clips")],
			});
			expect(p.type).toBe("review_completed");
			expect(p.isReadOnly).toBe(true);
			expect(p.showApproveReject).toBe(false);
		});
	});

	describe("asset retrieval counts", () => {
		it("shows matched/unresolved/blank counts", () => {
			const p = computePhasePresentation({
				phase: "asset_retrieving",
				execution: exec("succeeded"),
				requiredArtifactKinds: ["selected_clips"],
				artifacts: [artifact("selected_clips")],
				assetRetrievalCounts: { matched: 2, unresolved: 3, blank: 1 },
			});
			expect(p.type).toBe("succeeded");
			expect(p.message).toBe(
				"检索完成，共 6 句：已匹配 2 句、未匹配 3 句、留空 1 句。",
			);
		});

		it("zero matches is a normal result that enters asset review", () => {
			const p = computePhasePresentation({
				phase: "asset_retrieving",
				execution: exec("succeeded"),
				requiredArtifactKinds: ["selected_clips"],
				artifacts: [artifact("selected_clips")],
				assetRetrievalCounts: { matched: 0, unresolved: 5, blank: 0 },
			});
			expect(p.type).toBe("succeeded");
			expect(p.message).toContain("已匹配 0 句");
			expect(p.message).toContain("未匹配 5 句");
		});
	});

	describe("non-review generation phases", () => {
		it("tts_generating succeeded with audio is plain succeeded", () => {
			const p = computePhasePresentation({
				phase: "tts_generating",
				execution: exec("succeeded"),
				requiredArtifactKinds: ["tts_audio"],
				artifacts: [artifact("tts_audio")],
			});
			expect(p.type).toBe("succeeded");
			expect(p.title).toBe("TTS 配音完成");
		});

		it("tts_generating succeeded without audio is anomaly with retry", () => {
			const p = computePhasePresentation({
				phase: "tts_generating",
				execution: exec("succeeded"),
				requiredArtifactKinds: ["tts_audio"],
				artifacts: [],
			});
			expect(p.type).toBe("anomaly_missing_artifact");
			expect(p.showRetry).toBe(true);
		});
	});
});
