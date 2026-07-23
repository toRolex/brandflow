import { useState } from "react";

interface ClipData {
	sentence: string;
	sentence_index?: number;
	category: string;
	requested_category?: string;
	file_path: string;
	asset_id: string;
	duration_seconds?: number;
	method: string;
	visual_type?: "clip" | "blank" | "unresolved";
}

interface Props {
	clip: ClipData;
	index: number;
	onReject: (index: number) => void;
	onToggleBlank: (index: number) => void;
	onRestore: (index: number) => void;
	onSelectAsset: (index: number) => void;
	rejected?: boolean;
	readOnly?: boolean;
}

/** Map visual_type to display label and color class. */
function visualTypeInfo(vt: string | undefined): {
	label: string;
	bgClass: string;
	textClass: string;
} {
	switch (vt) {
		case "clip":
			return {
				label: "素材",
				bgClass: "bg-[var(--badge-default-bg)]",
				textClass: "text-[var(--color-signal-green)]",
			};
		case "blank":
			return {
				label: "黑帧",
				bgClass: "bg-gray-900",
				textClass: "text-gray-400",
			};
		case "unresolved":
			return {
				label: "待处理",
				bgClass: "bg-[var(--color-caution-amber)]/10",
				textClass: "text-[var(--color-caution-amber)]",
			};
		default:
			return {
				label: "未知",
				bgClass: "bg-[var(--badge-default-bg)]",
				textClass: "text-[var(--text-tertiary)]",
			};
	}
}

export default function ClipReviewCard({
	clip,
	index,
	onReject,
	onToggleBlank,
	onRestore,
	onSelectAsset,
	rejected = false,
	readOnly = false,
}: Props) {
	const [imgError, setImgError] = useState(false);
	const visualType = clip.visual_type || "unresolved";
	const vtInfo = visualTypeInfo(visualType);
	const thumbnailUrl = clip.asset_id
		? `/api/assets/${clip.asset_id}/thumbnail`
		: null;
	const fileName = clip.file_path.split("/").pop() || clip.asset_id;

	const isFallback = clip.method === "fallback";
	const hasDowngradeInfo =
		isFallback &&
		clip.requested_category &&
		clip.requested_category !== clip.category;

	const isBlank = visualType === "blank";
	const isUnresolved = visualType === "unresolved";
	const hasOriginal = clip.method !== "blank" && clip.file_path !== "";

	return (
		<div
			className={`border rounded-lg overflow-hidden transition-colors max-w-full ${
				rejected
					? "border-[var(--danger-border)] bg-[var(--danger-bg)]"
					: isBlank
						? "border-gray-600 bg-gray-950"
						: isUnresolved
							? "border-[var(--color-caution-amber)] bg-[var(--color-caution-amber)]/5"
							: "border-[var(--border-default)] bg-white"
			}`}
		>
			{/* Header: index + sentence + visual_type badge */}
			<div className="p-3 bg-[var(--bg-table-head)] border-b border-[var(--border-default)]">
				<div className="flex items-start gap-2">
					<span className="text-[var(--text-tertiary)] text-xs font-mono shrink-0">
						#{index + 1}
					</span>
					<p className="text-sm text-[var(--text-primary)] leading-relaxed break-words flex-1">
						{clip.sentence}
					</p>
				</div>
				<div className="flex flex-wrap items-center gap-2 mt-2">
					{/* Visual type badge */}
					<span
						className={`inline-flex px-1.5 py-0.5 rounded text-xs font-medium ${vtInfo.bgClass} ${vtInfo.textClass}`}
					>
						{vtInfo.label}
					</span>
					{clip.category && (
						<span className="inline-flex px-1.5 py-0.5 rounded text-xs bg-[var(--badge-default-bg)] text-[var(--text-secondary)]">
							{clip.category}
						</span>
					)}
					{hasDowngradeInfo ? (
						<span className="text-xs text-[var(--text-tag-yellow)]">
							想匹配：{clip.requested_category} → 降级为：{clip.category}
						</span>
					) : (
						clip.method &&
						!isBlank &&
						!isUnresolved && (
							<span
								className={`text-xs ${clip.method === "llm_match" ? "text-[var(--color-signal-green)]" : "text-[var(--text-tag-yellow)]"}`}
							>
								{clip.method === "llm_match"
									? "LLM 匹配"
									: clip.method === "manual"
										? "手动指定"
										: "降级匹配"}
							</span>
						)
					)}
				</div>
			</div>

			{/* Body: thumbnail or black frame placeholder */}
			<div className="p-3">
				<div className="flex items-center gap-3 mb-2">
					<div
						className={`w-20 h-14 rounded overflow-hidden flex-shrink-0 ${
							isBlank
								? "bg-black border border-gray-700"
								: "bg-[var(--bg-page)]"
						}`}
					>
						{isBlank ? (
							<div className="w-full h-full flex items-center justify-center">
								<span className="text-gray-600 text-xs">黑帧</span>
							</div>
						) : thumbnailUrl && !imgError ? (
							<img
								src={thumbnailUrl}
								alt={fileName}
								className="w-full h-full object-cover"
								onError={() => setImgError(true)}
							/>
						) : (
							<div className="w-full h-full flex items-center justify-center text-lg">
								{isUnresolved ? "⊘" : "🎬"}
							</div>
						)}
					</div>
					<div className="flex-1 min-w-0 overflow-hidden">
						{isBlank ? (
							<div className="text-xs text-gray-500 italic">
								此句留空 — 渲染时输出黑帧
							</div>
						) : isUnresolved ? (
							<div className="text-xs text-[var(--color-caution-amber)]">
								未匹配到素材，请手动选择或留空
							</div>
						) : (
							<>
								<div className="text-xs font-medium truncate" title={fileName}>
									{fileName}
								</div>
								<div className="text-xs text-gray-500 mt-0.5 truncate">
									{clip.asset_id}
								</div>
							</>
						)}
					</div>
				</div>

				{/* Actions */}
				{!readOnly && (
					<div className="flex flex-wrap gap-1.5">
						{!isBlank && (
							<button
								type="button"
								className="flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]"
								onClick={() => onSelectAsset(index)}
							>
								选择素材
							</button>
						)}
						{isBlank ? (
							<>
								<button
									type="button"
									className="flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors bg-[var(--btn-primary-bg)] text-white hover:brightness-110"
									onClick={() => onToggleBlank(index)}
								>
									恢复为素材
								</button>
								{hasOriginal && (
									<button
										type="button"
										className="flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]"
										onClick={() => onRestore(index)}
									>
										恢复原始选择
									</button>
								)}
							</>
						) : (
							<>
								<button
									type="button"
									className="flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors bg-[var(--btn-danger-bg)] text-white hover:bg-[var(--btn-danger-hover)]"
									onClick={() => onReject(index)}
								>
									打回检索
								</button>
								<button
									type="button"
									className="flex-1 px-3 py-1.5 rounded text-xs font-medium transition-colors border border-gray-600 text-gray-400 hover:bg-gray-800"
									onClick={() => onToggleBlank(index)}
								>
									留空（黑帧）
								</button>
								{hasOriginal && (
									<button
										type="button"
										className="px-3 py-1.5 rounded text-xs font-medium transition-colors border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]"
										onClick={() => onRestore(index)}
									>
										恢复
									</button>
								)}
							</>
						)}
					</div>
				)}
			</div>
		</div>
	);
}
