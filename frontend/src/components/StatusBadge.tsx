import type { Phase } from "../types";

type BadgeVariant = "default" | "success" | "warning" | "danger" | "neutral";

const VARIANT_MAP: Record<string, BadgeVariant> = {
	// default (electric-blue-muted / electric-blue)
	queued: "default",
	script_generating: "default",
	tts_generating: "default",
	subtitle_generating: "default",
	asset_retrieving: "default",
	video_rendering: "default",
	schedule_writing: "default",
	scene_assembling: "default",
	montage_assembling: "default",
	final_rendering: "default",
	migration_required: "default",
	// warning (caution-amber-muted / caution-amber)
	script_review: "warning",
	asset_review: "warning",
	final_review: "warning",
	tts_review: "warning",
	// success (signal-green-muted / signal-green)
	completed: "success",
	// danger (alert-red-muted / alert-red)
	failed: "danger",
	// neutral (--bg-nav-active / --text-tertiary)
	cancelled: "neutral",
	paused: "neutral",
};

const LABEL_MAP: Record<string, string> = {
	queued: "排队中",
	script_generating: "生成脚本",
	script_review: "待审核",
	tts_generating: "配音中",
	tts_review: "配音审核",
	subtitle_generating: "字幕中",
	asset_retrieving: "取素材",
	asset_review: "素材审核",
	video_rendering: "视频合成",
	final_review: "最终审核",
	schedule_writing: "写排期",
	scene_assembling: "场景拼接",
	montage_assembling: "蒙太奇",
	final_rendering: "终审·合成",
	migration_required: "需补充场景",
	completed: "已完成",
	failed: "失败",
	cancelled: "已取消",
	paused: "已暂停",
};

const BASE_STYLE: React.CSSProperties = {
	display: "inline-block",
	padding: "var(--badge-padding, 2px 8px)",
	borderRadius: "var(--radius-sm, 4px)",
	fontFamily: "var(--font-family-label)",
	fontSize: "0.75rem",
	fontWeight: 500,
	lineHeight: 1.3,
	letterSpacing: "var(--font-label-spacing, 0.02em)",
};

const VARIANT_STYLES: Record<BadgeVariant, React.CSSProperties> = {
	default: {
		backgroundColor: "var(--badge-default-bg)",
		color: "var(--badge-default-text)",
	},
	success: {
		backgroundColor: "var(--badge-success-bg)",
		color: "var(--badge-success-text)",
	},
	warning: {
		backgroundColor: "var(--badge-warning-bg)",
		color: "var(--badge-warning-text)",
	},
	danger: {
		backgroundColor: "var(--badge-danger-bg)",
		color: "var(--badge-danger-text)",
	},
	neutral: {
		backgroundColor: "var(--bg-nav-active)",
		color: "var(--text-tertiary)",
	},
};

export default function StatusBadge({ phase }: { phase: Phase }) {
	const variant = VARIANT_MAP[phase] || "default";

	return (
		<span style={{ ...BASE_STYLE, ...VARIANT_STYLES[variant] }}>
			{LABEL_MAP[phase] || phase}
		</span>
	);
}
