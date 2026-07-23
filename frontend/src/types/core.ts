export type ProductionMode = "import" | "generate";
export type ReviewStrategy = "review_each" | "fast_output";

export const KNOWN_PHASES = [
	"draft",
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
	"completed",
	"failed",
	"cancelled",
	"paused",
] as const;

export type Phase = (typeof KNOWN_PHASES)[number];

export type ReviewStatus =
	| "none"
	| "pending"
	| "approved"
	| "rejected"
	| "overridden";

export interface ExecutionFailure {
	code: string;
	message: string;
	retryable: boolean;
}

export interface PhaseExecutionState {
	status: "pending" | "running" | "retrying" | "failed" | "succeeded";
	current_attempt: number;
	max_attempts: number;
	error: ExecutionFailure | null;
}

export interface Artifact {
	kind: string;
	relative_path: string;
	url: string;
}

export interface CoverTitle {
	text: string;
	highlight_words?: string[];
	style?: {
		primary_color?: string;
		outline_color?: string;
		highlight_color?: string;
		outline_width?: number;
		position?: string;
	};
}

export interface PipelineStep {
	key: string;
	phase: Phase;
	label: string;
	isReview: boolean;
}

export const PIPELINE_STEPS: PipelineStep[] = [
	{ key: "draft", phase: "draft", label: "草稿", isReview: false },
	{ key: "queued", phase: "queued", label: "排队中", isReview: false },
	{
		key: "scene_assemble",
		phase: "scene_assembling",
		label: "场景拼接",
		isReview: false,
	},
	{
		key: "script_gen",
		phase: "script_generating",
		label: "生成脚本",
		isReview: false,
	},
	{
		key: "script_review",
		phase: "script_review",
		label: "脚本审核",
		isReview: true,
	},
	{ key: "tts", phase: "tts_generating", label: "TTS 配音", isReview: false },
	{ key: "tts_review", phase: "tts_review", label: "TTS 审核", isReview: true },
	{
		key: "subtitle",
		phase: "subtitle_generating",
		label: "转录字幕",
		isReview: false,
	},
	{
		key: "asset_retrieving",
		phase: "asset_retrieving",
		label: "素材检索",
		isReview: false,
	},
	{
		key: "asset_review",
		phase: "asset_review",
		label: "素材审核",
		isReview: true,
	},
	{
		key: "montage",
		phase: "montage_assembling",
		label: "蒙太奇",
		isReview: false,
	},
	{
		key: "video_base",
		phase: "video_rendering",
		label: "底包拼接",
		isReview: false,
	},
	{
		key: "final_render",
		phase: "final_rendering",
		label: "终审·合成",
		isReview: false,
	},
	{
		key: "final_review",
		phase: "final_review",
		label: "终审·烧录",
		isReview: true,
	},
	{ key: "completed", phase: "completed", label: "已完成", isReview: false },
	{ key: "failed", phase: "failed", label: "已失败", isReview: false },
	{ key: "cancelled", phase: "cancelled", label: "已取消", isReview: false },
	{ key: "paused", phase: "paused", label: "已暂停", isReview: false },
];
