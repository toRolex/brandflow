import { useEffect, useState } from "react";
import { api } from "../../../api/client";
import ClipReviewCard from "../../../components/ClipReviewCard";
import type { AssetRecord } from "../../../types";
import type { PanelProps } from "../types";

export default function AssetReviewPanel({
	job,
	selectedClips,
	rejectedClips,
	showAllBlankConfirm,
	isCurrentReviewStep,
	onReject,
	onRejectClip,
	onToggleBlank,
	onRestoreClip,
	onSelectAsset,
	onAssetApprove,
	onForceApprove,
	onDismissAllBlankConfirm,
	findArtifact,
}: PanelProps) {
	const clipsArtifact = findArtifact("selected_clips");
	const [pickerIndex, setPickerIndex] = useState<number | null>(null);
	const [pickerAssets, setPickerAssets] = useState<AssetRecord[]>([]);
	const [pickerLoading, setPickerLoading] = useState(false);

	useEffect(() => {
		if (pickerIndex === null) return;
		setPickerLoading(true);
		api
			.listIndexedAssetsShared({ product: job.product })
			.then((result) =>
				setPickerAssets(
					result.assets.filter((asset) => asset.status === "available"),
				),
			)
			.catch(() => setPickerAssets([]))
			.finally(() => setPickerLoading(false));
	}, [job.product, pickerIndex]);

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
										(clip.visual_type as "clip" | "blank" | "unresolved") ||
										"unresolved",
								}}
								index={index}
								onReject={onRejectClip}
								onToggleBlank={onToggleBlank}
								onRestore={onRestoreClip}
								onSelectAsset={setPickerIndex}
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
				<p className="text-[var(--text-tertiary)] text-sm">等待素材加载...</p>
			)}
			{pickerIndex !== null && (
				<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
					<div className="w-full max-w-2xl max-h-[80vh] overflow-auto rounded-lg bg-[var(--bg-card)] p-5 shadow-xl">
						<div className="mb-4 flex items-center justify-between">
							<h4 className="font-semibold">选择库内素材</h4>
							<button onClick={() => setPickerIndex(null)}>关闭</button>
						</div>
						{pickerLoading ? (
							<p className="text-sm text-[var(--text-tertiary)]">加载素材中…</p>
						) : pickerAssets.length === 0 ? (
							<p className="text-sm text-[var(--text-tertiary)]">
								没有可用素材
							</p>
						) : (
							<div className="grid gap-2 sm:grid-cols-2">
								{pickerAssets.map((asset) => (
									<button
										key={asset.asset_id}
										className="rounded border p-3 text-left hover:bg-[var(--bg-table-head)]"
										onClick={() => {
											onSelectAsset(pickerIndex, asset.asset_id);
											setPickerIndex(null);
										}}
									>
										<div className="text-sm font-medium">
											{asset.file_path.split("/").pop()}
										</div>
										<div className="text-xs text-[var(--text-secondary)]">
											{asset.category} · {asset.duration_seconds.toFixed(1)}s
										</div>
									</button>
								))}
							</div>
						)}
					</div>
				</div>
			)}
		</div>
	);
}
