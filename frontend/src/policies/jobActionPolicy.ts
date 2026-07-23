import type { JobDetail } from "../types";

export interface JobActionPolicy {
	canPause: boolean;
	canResume: boolean;
	canCancel: boolean;
	canRetry: boolean;
	pauseMessage: string | null;
	retryMessage: string | null;
}

const ACTIVE_PHASES = new Set([
	"queued",
	"script_generating",
	"script_review",
	"scene_assembling",
	"tts_generating",
	"tts_review",
	"subtitle_generating",
	"asset_retrieving",
	"asset_review",
	"montage_assembling",
	"video_rendering",
	"final_rendering",
	"final_review",
]);

/** Single UI source of truth for lifecycle actions and their explanations. */
export function getJobActionPolicy(job: JobDetail): JobActionPolicy {
	const active = ACTIVE_PHASES.has(job.phase);
	const pauseMessage = job.pause_requested
		? "暂停请求已登记；当前阶段完成后将停止推进。"
		: null;
	const retryable = job.execution.error?.retryable === true;

	return {
		canPause: active && !job.pause_requested,
		canResume: job.phase === "paused" && Boolean(job.paused_from_phase),
		canCancel: active || job.phase === "paused",
		canRetry: job.phase === "failed" && retryable,
		pauseMessage,
		retryMessage:
			job.phase === "failed"
				? retryable
					? null
					: "此失败不可重试；请先修复对应的配置或输入。"
				: "仅失败的 Job 可以重新执行失败阶段。",
	};
}
