import AssetGrid from "../../../components/AssetGrid";
import { presentPhaseStatus } from "../phasePresentation";
import type { PanelProps } from "../types";

export default function AssetRetrievingPanel({
	job,
	selectedClips,
	selectedClipsLoadState,
}: PanelProps) {
	const decisionCounts = selectedClips.reduce<{
		total: number;
		clip: number;
		unresolved: number;
		blank: number;
	}>(
		(counts, clip) => {
			const decision = String(clip.visual_type || "unresolved");
			if (decision === "clip" || decision === "blank" || decision === "unresolved") {
				counts[decision] += 1;
			}
			counts.total += 1;
			return counts;
		},
		{ total: 0, clip: 0, unresolved: 0, blank: 0 },
	);
	const presentation = presentPhaseStatus({
		phase: job.phase,
		execution: job.execution,
		reviewStatus: job.review_status,
		artifacts: job.artifacts,
		assetDecisions: decisionCounts,
		artifactLoadState: selectedClipsLoadState,
	});
	const assetRecords = selectedClips.map((clip, index) => ({
		asset_id: String(clip.asset_id || `clip-${index}`),
		file_path: String(clip.file_path || ""),
		category: String(clip.category || ""),
		product: "",
		confidence: 1,
		duration_seconds: 0,
		status: "available" as const,
		usage_count: 0,
		source_video: "",
		tags: clip.sentence ? [String(clip.sentence)] : [],
		created_at: "",
		last_used_at: "",
	}));

	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">素材检索</h3>
			{presentation.kind === "running" && (
				<div className="py-4">
					<div className="flex items-center gap-2 mb-2">
						<div
							className="w-4 h-4 border-2 rounded-full animate-spin"
							style={{ borderColor: "var(--border-default)", borderTopColor: "var(--btn-primary-bg)" }}
						/>
						<p className="text-[var(--text-tertiary)] text-sm">{presentation.title}</p>
					</div>
					<p className="text-[var(--text-tertiary)] text-xs">
						第 {job.execution.current_attempt} / {job.execution.max_attempts} 次尝试
					</p>
				</div>
			)}
			{["waiting", "retrying", "awaiting_review"].includes(presentation.kind) && (
				<div className="py-4">
					<p className="text-[var(--text-tertiary)] text-sm">{presentation.title}</p>
					<p className="text-[var(--text-tertiary)] text-xs mt-1">{presentation.detail}</p>
				</div>
			)}
			{presentation.kind === "integrity_error" && (
				<div className="py-4">
					<div className="p-3 rounded-lg border" style={{ borderColor: "var(--alert-red)", background: "var(--alert-red-muted)" }}>
						<p className="text-sm font-medium" style={{ color: "var(--alert-red)" }}>{presentation.title}</p>
						<p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>{presentation.detail}</p>
					</div>
				</div>
			)}
			{["completed", "needs_business_decision"].includes(presentation.kind) && (
				<div>
					<p className="text-[var(--text-tertiary)] text-sm mb-4">{presentation.detail}</p>
					<div className="max-h-[500px] overflow-y-auto">
						<AssetGrid assets={assetRecords} selectedIds={new Set()} onToggleSelect={() => {}} onPreview={() => {}} />
					</div>
				</div>
			)}
		</div>
	);
}
