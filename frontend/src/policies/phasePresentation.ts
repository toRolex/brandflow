import type {
	Artifact,
	Phase,
	PhaseExecutionState,
	ReviewStatus,
} from "../types/core";
import { PIPELINE_STEPS } from "../types/core";

export type PresentationType =
	| "pending"
	| "running"
	| "retrying"
	| "failed"
	| "succeeded"
	| "review_ready"
	| "review_completed"
	| "anomaly_missing_artifact"
	| "completed"
	| "unknown";

export type PresentationSeverity = "info" | "success" | "warning" | "error";

export type SuggestedActionKey =
	| "retry"
	| "approve"
	| "reject"
	| "review"
	| "contact"
	| "reload"
	| "diagnose";

export interface SuggestedAction {
	key: SuggestedActionKey;
	label: string;
}

export interface PhasePresentation {
	type: PresentationType;
	title: string;
	message: string;
	severity: PresentationSeverity;
	/** When true, panel-specific interactive controls should be disabled. */
	isReadOnly: boolean;
	/** Show a manual retry button (only valid after terminal failure or recoverable anomaly). */
	showRetry: boolean;
	/** Show approve/reject controls (review phases only). */
	showApproveReject: boolean;
	retryAttempt?: number;
	maxRetryAttempts?: number;
	errorCode?: string;
	errorMessage?: string;
	actions: SuggestedAction[];
}

export interface ComputePhasePresentationInput {
	phase: Phase;
	execution: PhaseExecutionState;
	reviewStatus?: ReviewStatus;
	requiredArtifactKinds?: string[];
	artifacts?: Artifact[];
	phaseLabel?: string;
	assetRetrievalCounts?: {
		matched: number;
		unresolved: number;
		blank: number;
	};
}

const EXECUTABLE_GENERATION_PHASES: Set<Phase> = new Set([
	"script_generating",
	"scene_assembling",
	"tts_generating",
	"subtitle_generating",
	"asset_retrieving",
	"montage_assembling",
	"video_rendering",
	"final_rendering",
]);

function getPhaseLabel(phase: Phase): string {
	const step = PIPELINE_STEPS.find((s) => s.phase === phase);
	return step?.label || "未知阶段";
}

function isReviewPhase(phase: Phase): boolean {
	return PIPELINE_STEPS.find((s) => s.phase === phase)?.isReview ?? false;
}

function findMissingArtifactKinds(
	required: string[] | undefined,
	artifacts: Artifact[] | undefined,
): string[] {
	if (!required || required.length === 0) return [];
	const present = new Set(artifacts?.map((a) => a.kind) ?? []);
	return required.filter((kind) => !present.has(kind));
}

function buildAnomalyPresentation(
	phase: Phase,
	phaseLabel: string,
	missingKinds: string[],
	execution: PhaseExecutionState,
): PhasePresentation {
	const isGeneration = EXECUTABLE_GENERATION_PHASES.has(phase);
	const isReview = isReviewPhase(phase);
	const kindLabel = missingKinds
		.map((k) => artifactKindDisplayName(k))
		.join("、");
	const title =
		phase === "completed"
			? "完成记录不完整"
			: isReview
				? `${phaseLabel}输入缺失`
				: `${phaseLabel}结果异常`;
	const message =
		phase === "completed"
			? "最终视频产物缺失，无法导出。请检查渲染日志或联系支持。"
			: `${phaseLabel}已结束，但缺少必要产物：${kindLabel}。请尝试重新执行或查看日志。`;
	const actions: SuggestedAction[] = [];
	if (isGeneration) {
		actions.push({ key: "retry", label: "重试" });
	}
	actions.push({ key: "diagnose", label: "查看日志" });
	actions.push({ key: "contact", label: "联系支持" });

	return {
		type: "anomaly_missing_artifact",
		title,
		message,
		severity: "warning",
		isReadOnly: true,
		showRetry: isGeneration,
		showApproveReject: false,
		retryAttempt: execution.current_attempt,
		maxRetryAttempts: execution.max_attempts,
		actions,
	};
}

function artifactKindDisplayName(kind: string): string {
	switch (kind) {
		case "script":
			return "脚本";
		case "tts_audio":
			return "TTS 音频";
		case "subtitle":
			return "字幕";
		case "selected_clips":
			return "已选素材";
		case "video_base":
			return "底包视频";
		case "final_video":
			return "最终视频";
		default:
			return kind;
	}
}

export function computePhasePresentation({
	phase,
	execution,
	reviewStatus,
	requiredArtifactKinds,
	artifacts,
	phaseLabel: explicitLabel,
	assetRetrievalCounts,
}: ComputePhasePresentationInput): PhasePresentation {
	const phaseLabel = explicitLabel ?? getPhaseLabel(phase);
	const status = execution.status ?? "unknown";

	// 1. Terminal failure has the highest priority.
	if (status === "failed") {
		const retryable = execution.error?.retryable ?? false;
		const actions: SuggestedAction[] = [];
		if (retryable) {
			actions.push({ key: "retry", label: "重试" });
		}
		actions.push({ key: "diagnose", label: "查看日志" });
		return {
			type: "failed",
			title: `${phaseLabel}失败`,
			message: execution.error
				? `阶段执行失败：${execution.error.message}${execution.error.code ? `（${execution.error.code}）` : ""}`
				: "阶段执行失败，请查看日志。",
			severity: "error",
			isReadOnly: true,
			showRetry: retryable,
			showApproveReject: false,
			retryAttempt: execution.current_attempt,
			maxRetryAttempts: execution.max_attempts,
			errorCode: execution.error?.code,
			errorMessage: execution.error?.message,
			actions,
		};
	}

	// 2. Auto-retrying must never be misrepresented as "waiting".
	if (status === "retrying") {
		return {
			type: "retrying",
			title: "正在自动重试",
			message: `系统正在自动重试：第 ${execution.current_attempt} / ${execution.max_attempts} 次尝试。${execution.error ? `最近错误：${execution.error.message}${execution.error.code ? `（${execution.error.code}）` : ""}` : ""}`,
			severity: "warning",
			isReadOnly: true,
			showRetry: false,
			showApproveReject: false,
			retryAttempt: execution.current_attempt,
			maxRetryAttempts: execution.max_attempts,
			errorCode: execution.error?.code,
			errorMessage: execution.error?.message,
			actions: [{ key: "reload", label: "刷新状态" }],
		};
	}

	// 3. Running.
	if (status === "running") {
		return {
			type: "running",
			title: `正在${phaseLabel}`,
			message: `正在执行${phaseLabel}…（第 ${execution.current_attempt} / ${execution.max_attempts} 次尝试）`,
			severity: "info",
			isReadOnly: true,
			showRetry: false,
			showApproveReject: false,
			retryAttempt: execution.current_attempt,
			maxRetryAttempts: execution.max_attempts,
			actions: [],
		};
	}

	// 4. Pending / unknown.
	if (status === "pending" || !status) {
		return {
			type: "pending",
			title: `等待${phaseLabel}`,
			message: `等待开始${phaseLabel}…`,
			severity: "info",
			isReadOnly: true,
			showRetry: false,
			showApproveReject: false,
			actions: [],
		};
	}

	// 5. Succeeded: check artifact completeness before declaring success.
	if (status === "succeeded") {
		const missingKinds = findMissingArtifactKinds(
			requiredArtifactKinds,
			artifacts,
		);
		if (missingKinds.length > 0) {
			return buildAnomalyPresentation(
				phase,
				phaseLabel,
				missingKinds,
				execution,
			);
		}

		// Completed phase is special: final video must exist.
		if (phase === "completed") {
			return {
				type: "completed",
				title: "生产完成",
				message: "视频已生成并排期发布。",
				severity: "success",
				isReadOnly: false,
				showRetry: false,
				showApproveReject: false,
				actions: [{ key: "review", label: "查看导出" }],
			};
		}

		// Review phases: distinguish ready vs already decided.
		if (isReviewPhase(phase)) {
			if (reviewStatus === "pending") {
				return {
					type: "review_ready",
					title: `等待${phaseLabel}`,
					message: `当前处于${phaseLabel}，请审核后作出决策。`,
					severity: "warning",
					isReadOnly: false,
					showRetry: false,
					showApproveReject: true,
					actions: [
						{ key: "approve", label: "通过" },
						{ key: "reject", label: "打回" },
					],
				};
			}
			return {
				type: "review_completed",
				title: `${phaseLabel}已完成`,
				message: `该审核阶段已${reviewStatus === "approved" ? "通过" : reviewStatus === "rejected" ? "打回" : "处理"}。`,
				severity: "info",
				isReadOnly: true,
				showRetry: false,
				showApproveReject: false,
				actions: [],
			};
		}

		// Asset retrieval succeeded: show counts.
		if (phase === "asset_retrieving" && assetRetrievalCounts) {
			const { matched, unresolved, blank } = assetRetrievalCounts;
			const total = matched + unresolved + blank;
			return {
				type: "succeeded",
				title: "素材检索完成",
				message: `检索完成，共 ${total} 句：已匹配 ${matched} 句、未匹配 ${unresolved} 句、留空 ${blank} 句。`,
				severity: "success",
				isReadOnly: false,
				showRetry: false,
				showApproveReject: false,
				actions: [{ key: "review", label: "进入审核" }],
			};
		}

		return {
			type: "succeeded",
			title: `${phaseLabel}完成`,
			message: `${phaseLabel}已完成，等待下一阶段…`,
			severity: "success",
			isReadOnly: false,
			showRetry: false,
			showApproveReject: false,
			actions: [],
		};
	}

	// Defensive fallback for unexpected status values.
	return {
		type: "unknown",
		title: phaseLabel,
		message: `未知状态：${status}，请刷新页面。`,
		severity: "warning",
		isReadOnly: true,
		showRetry: false,
		showApproveReject: false,
		actions: [{ key: "reload", label: "刷新" }],
	};
}
