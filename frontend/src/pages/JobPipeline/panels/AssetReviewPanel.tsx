import ClipReviewCard from "../../../components/ClipReviewCard";
import { PanelProps } from "../types";

export default function AssetReviewPanel({
	selectedClips,
	rejectedClips,
	showAllBlankConfirm,
	isCurrentReviewStep,
	onReject,
	onRejectClip,
	onToggleBlank,
	onRestoreClip,
	onAssetApprove,
	onForceApprove,
	onDismissAllBlankConfirm,
	findArtifact,
}: PanelProps) {
	const clipsArtifact = findArtifact("selected_clips");

	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">素材审核</h3>
			{clipsArtifact && selectedClips.length > 0 ? (
				<div>
					<p className="text-[var(--text-tertiary)] text-sm mb-4">
						请审核检索到的 {selectedClips.length} 个素材
						{rejectedClips.size > 0 && (
							<span className="text-[var(--color-alert-red)]">
								（已打回 {rejectedClips.size} 个）
							</span>
						)}
					</p>
					<div className="max-h-[600px] overflow-y-auto overflow-x-hidden space-y-3 mb-4">
						{selectedClips.map((clip, index) => (
							<ClipReviewCard
								key={`${clip.asset_id}-${index}`}
								clip={{
									sentence: String(clip.sentence || ""),
									sentence_index:
										clip.sentence_index == null
											? undefined
											: Number(clip.sentence_index),
									category: String(clip.category || ""),
									requested_category: clip.requested_category
										? String(clip.requested_category)
										: undefined,
									file_path: String(clip.file_path || ""),
									asset_id: String(clip.asset_id || ""),
									duration_seconds: clip.duration_seconds
										? Number(clip.duration_seconds)
										: undefined,
									method: String(clip.method || ""),
									visual_type:
										(clip.visual_type as
											| "clip"
											| "blank"
											| "unresolved") || "unresolved",
								}}
								index={index}
								onReject={onRejectClip}
								onToggleBlank={onToggleBlank}
								onRestore={onRestoreClip}
								rejected={rejectedClips.has(index)}
								readOnly={!isCurrentReviewStep}
							/>
						))}
					</div>
					{!isCurrentReviewStep && (
						<div
							className="text-xs mb-2"
							style={{ color: "var(--color-caution-amber)" }}
						>
							当前不在该审核阶段，无法操作
						</div>
					)}
					<div className="flex gap-2">
						<button
							className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
							onClick={onAssetApprove}
							disabled={!isCurrentReviewStep}
							aria-disabled={!isCurrentReviewStep}
						>
							{"✓"} 全部通过
						</button>
						<button
							className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
							onClick={() => onReject("asset_review")}
							disabled={!isCurrentReviewStep}
							aria-disabled={!isCurrentReviewStep}
						>
							{"✗"} 全部打回重新检索
						</button>
					</div>

					{showAllBlankConfirm && (
						<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
							<div className="bg-white rounded-lg shadow-xl p-6 max-w-md mx-4">
								<h4 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
									确认全留空审批
								</h4>
								<p className="text-sm text-[var(--text-secondary)] mb-4">
									所有 {selectedClips.length}{" "}
									个句子均已标记为"黑帧"（留空）。确认后每个句子位置将渲染黑帧（无画面），您仍可在正式渲染前恢复素材选择。
								</p>
								<div className="flex gap-2 justify-end">
									<button
										className="px-4 py-2 rounded-md text-xs border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]"
										onClick={onDismissAllBlankConfirm}
									>
										取消
									</button>
									<button
										className="px-4 py-2 rounded-md text-xs bg-[var(--btn-primary-bg)] text-white hover:brightness-110"
										onClick={onForceApprove}
									>
										确认留空 (force=true)
									</button>
								</div>
							</div>
						</div>
					)}
				</div>
			) : (
				<p className="text-[var(--text-tertiary)] text-sm">
					等待素材加载...
				</p>
			)}
		</div>
	);
}
