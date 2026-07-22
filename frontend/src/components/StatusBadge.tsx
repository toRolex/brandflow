import { type Phase, PIPELINE_STEPS } from "../types";

type BadgeVariant = "default" | "success" | "warning" | "danger" | "neutral";

const VARIANT_MAP: Record<string, BadgeVariant> = {
	// default (electric-blue-muted / electric-blue)
	queued: "default",
	script_generating: "default",
	tts_generating: "default",
	subtitle_generating: "default",
	asset_retrieving: "default",
	video_rendering: "default",
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

const PIPELINE_LABELS = Object.fromEntries(
	PIPELINE_STEPS.map((step) => [step.phase, step.label]),
) as Partial<Record<Phase, string>>;

const LABEL_OVERRIDES: Partial<Record<Phase, string>> = {
	script_review: "待审核",
	tts_generating: "配音中",
	tts_review: "配音审核",
	subtitle_generating: "字幕中",
	asset_retrieving: "取素材",
	video_rendering: "视频合成",
	final_review: "最终审核",
	failed: "失败",
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
			{LABEL_OVERRIDES[phase] || PIPELINE_LABELS[phase] || phase}
		</span>
	);
}
