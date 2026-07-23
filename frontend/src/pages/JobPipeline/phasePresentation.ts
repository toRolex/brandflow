import type {
	Artifact,
	Phase,
	PhaseExecutionState,
	ReviewStatus,
} from "../../types";

export type PhasePresentationKind =
	| "waiting"
	| "running"
	| "retrying"
	| "awaiting_review"
	| "needs_business_decision"
	| "recoverable_error"
	| "failed"
	| "integrity_error"
	| "completed";

export type PhasePresentationAction =
	| "wait"
	| "wait_for_retry"
	| "review"
	| "review_assets"
	| "retry"
	| "view_logs"
	| "none";

export interface AssetDecisionCounts {
	total: number;
	clip: number;
	unresolved: number;
	blank: number;
}

export interface PhasePresentationInput {
	phase: Phase;
	execution: PhaseExecutionState;
	reviewStatus: ReviewStatus;
	artifacts: Artifact[];
	requiredArtifacts?: string[];
	assetDecisions?: AssetDecisionCounts;
	artifactLoadState?: "idle" | "loading" | "ready" | "failed";
}

export interface PhasePresentation {
	kind: PhasePresentationKind;
	title: string;
	detail: string;
	action: PhasePresentationAction;
}

function missingArtifacts(input: PhasePresentationInput): string[] {
	const defaults: Partial<Record<Phase, string[]>> = {
		script_review: ["script"],
		tts_review: ["tts_audio"],
		subtitle_generating: ["subtitle"],
		asset_retrieving: ["selected_clips"],
		asset_review: ["selected_clips"],
		video_rendering: ["video_base"],
		final_rendering: ["final_video"],
		final_review: ["final_video"],
		completed: ["final_video"],
	};
	return (input.requiredArtifacts ?? defaults[input.phase] ?? []).filter(
		(kind) => !input.artifacts.some((artifact) => artifact.kind === kind),
	);
}

export function presentPhaseStatus(
	input: PhasePresentationInput,
): PhasePresentation {
	const { execution } = input;

	if (input.phase === "cancelled") {
		return {
			kind: "failed",
			title: "任务已取消",
			detail: "任务不会继续执行。",
			action: "none",
		};
	}
	if (input.phase === "failed" || execution.status === "failed") {
		const retryable = execution.error?.retryable;
		return {
			kind: retryable ? "recoverable_error" : "failed",
			title: retryable ? "阶段执行失败，可恢复" : "阶段执行失败",
			detail: execution.error?.message ?? "执行未返回可用结果。",
			action: retryable ? "retry" : "view_logs",
		};
	}
	if (execution.status === "retrying") {
		return {
			kind: "retrying",
			title: "系统正在自动重试",
			detail: `第 ${execution.current_attempt}/${execution.max_attempts} 次尝试${execution.error ? `：${execution.error.message}` : ""}`,
			action: "wait_for_retry",
		};
	}
	if (execution.status === "running") {
		return {
			kind: "running",
			title: "正在执行",
			detail: "系统正在处理此阶段。",
			action: "wait",
		};
	}
	if (execution.status === "pending") {
		return {
			kind: "waiting",
			title: "等待开始",
			detail: "等待调度执行此阶段。",
			action: "wait",
		};
	}
	if (input.artifactLoadState === "loading") {
		return {
			kind: "waiting",
			title: "正在加载阶段结果",
			detail: "结果指针已返回，正在读取内容。",
			action: "wait",
		};
	}
	if (input.artifactLoadState === "failed") {
		return {
			kind: "integrity_error",
			title: "阶段结果无法加载",
			detail: "结果指针存在，但内容无法读取。请查看日志并重试。",
			action: "view_logs",
		};
	}

	const missing = missingArtifacts(input);
	if (missing.length > 0) {
		return {
			kind: "integrity_error",
			title: "阶段记录不完整",
			detail: `阶段已标记成功，但缺少必要产物：${missing.join("、")}。请查看日志并重试。`,
			action: "view_logs",
		};
	}
	if (input.reviewStatus === "pending") {
		return {
			kind: "awaiting_review",
			title: "等待人工审核",
			detail: "请作出审核决定后继续。",
			action: "review",
		};
	}
	if (input.assetDecisions?.unresolved) {
		return {
			kind: "needs_business_decision",
			title: "检索完成，等待素材决策",
			detail: `共 ${input.assetDecisions.total} 句：已匹配 ${input.assetDecisions.clip} 句，待处理 ${input.assetDecisions.unresolved} 句，留空 ${input.assetDecisions.blank} 句。`,
			action: "review_assets",
		};
	}
	return {
		kind: "completed",
		title: "阶段已完成",
		detail: "结果已就绪。",
		action: "none",
	};
}
