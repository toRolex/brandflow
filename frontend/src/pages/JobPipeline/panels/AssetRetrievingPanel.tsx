import AssetGrid from "../../../components/AssetGrid";
import { PanelProps } from "../types";

export default function AssetRetrievingPanel({
	job,
	selectedClips,
	onRetry,
	findArtifact,
}: PanelProps) {
	const execStatus = job.execution?.status;
	const clipsArtifact = findArtifact("selected_clips");
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

			{execStatus === "pending" && (
				<div className="py-4">
					<p className="text-[var(--text-tertiary)] text-sm">
						等待开始切配...
					</p>
				</div>
			)}

			{execStatus === "running" && (
				<div className="py-4">
					<div className="flex items-center gap-2 mb-2">
						<div
							className="w-4 h-4 border-2 rounded-full animate-spin"
							style={{
								borderColor: "var(--border-default)",
								borderTopColor: "var(--btn-primary-bg)",
							}}
						/>
						<p className="text-[var(--text-tertiary)] text-sm">
							正在切配素材...
						</p>
					</div>
					<p className="text-[var(--text-tertiary)] text-xs">
						第 {job.execution.current_attempt} / {job.execution.max_attempts}{" "}
						次重试
					</p>
				</div>
			)}

			{execStatus === "succeeded" && clipsArtifact && (
				<div>
					<p className="text-[var(--text-tertiary)] text-sm mb-4">
						已检索到 {selectedClips.length} 个匹配素材
					</p>
					<div className="max-h-[500px] overflow-y-auto">
						<AssetGrid
							assets={assetRecords}
							selectedIds={new Set()}
							onToggleSelect={() => {}}
							onPreview={() => {}}
						/>
					</div>
				</div>
			)}

			{execStatus === "succeeded" && !clipsArtifact && (
				<div className="py-4">
					<div
						className="p-3 rounded-lg border mb-3"
						style={{
							borderColor: "var(--color-caution-amber)",
							background: "var(--bg-table-head)",
						}}
					>
						<p
							className="text-sm font-medium"
							style={{ color: "var(--color-caution-amber)" }}
						>
							无可用素材
						</p>
						<p
							className="text-xs mt-1"
							style={{ color: "var(--text-secondary)" }}
						>
							未找到与当前文案匹配的素材。您可以修改文案后重试，或检查素材库内容。
						</p>
					</div>
					<button
						className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
						onClick={onRetry}
					>
						重新检索素材
					</button>
				</div>
			)}

			{!["pending", "running", "succeeded"].includes(execStatus || "") && (
				<p className="text-[var(--text-tertiary)] text-sm">
					等待素材检索...
				</p>
			)}
		</div>
	);
}
