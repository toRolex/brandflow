import { useState } from "react";
import type { AssetFile } from "../types";

type AssetCardData = AssetFile & {
	asset_id?: string;
	category?: string;
	confidence?: number;
	status?: string;
};

interface Props {
	asset: AssetCardData;
	onDelete?: (name: string) => void;
	selected?: boolean;
	onSelect?: (name: string, event: React.MouseEvent<HTMLButtonElement>) => void;
}

export default function AssetCard({
	asset,
	onDelete,
	selected = false,
	onSelect,
}: Props) {
	const [imgError, setImgError] = useState(false);
	const seconds = asset.duration_seconds || 0;
	const min = Math.floor(seconds / 60);
	const sec = String(Math.floor(seconds % 60)).padStart(2, "0");
	const confidence =
		typeof asset.confidence === "number"
			? `${Math.round(asset.confidence * 100)}%`
			: null;
	const isClassificationFailed = asset.status === "classification_failed";

	const containerStyle: React.CSSProperties = selected
		? { borderColor: "var(--accent)", background: "var(--bg-nav-active)" }
		: asset.in_use
			? { borderColor: "var(--success)", background: "var(--success-bg)" }
			: { borderColor: "var(--border-default)", background: "var(--bg-card)" };

	const isSelectable = Boolean(onSelect);
	const thumbnailUrl = asset.asset_id
		? `/api/assets/${asset.asset_id}/thumbnail`
		: null;

	return (
		<div
			className="w-44 text-left border rounded-lg overflow-hidden flex-shrink-0 transition-colors"
			style={containerStyle}
			role="group"
		>
			<div
				className="h-[124px] flex items-center justify-center overflow-hidden"
				style={{ background: "var(--bg-page)" }}
			>
				{thumbnailUrl && !imgError ? (
					<img
						src={thumbnailUrl}
						alt={asset.name}
						className="w-full h-full object-cover"
						onError={() => setImgError(true)}
						loading="lazy"
					/>
				) : (
					<span className="text-[28px]">{"🎬"}</span>
				)}
			</div>
			<div className="p-2 text-xs">
				<div className="font-medium truncate" title={asset.name}>
					{asset.name}
				</div>
				{isClassificationFailed ? (
					<div
						className="inline-flex mt-1 px-1.5 py-0.5 rounded"
						style={{
							background: "var(--danger-bg, #fef2f2)",
							color: "var(--danger, #dc2626)",
						}}
					>
						分类失败/待复核
					</div>
				) : (
					<>
						{asset.category && (
							<div
								className="inline-flex mt-1 px-1.5 py-0.5 rounded"
								style={{
									background: "var(--bg-nav-active)",
									color: "var(--text-secondary)",
								}}
							>
								{asset.category}
							</div>
						)}
						{confidence && (
							<div className="mt-0.5" style={{ color: "var(--accent)" }}>
								置信度 {confidence}
							</div>
						)}
					</>
				)}
				{seconds > 0 && (
					<div className="mt-1" style={{ color: "var(--text-secondary)" }}>
						{min}:{sec}
					</div>
				)}
				{asset.in_use && (
					<div className="mt-0.5" style={{ color: "var(--success)" }}>
						&#10003; 使用中
					</div>
				)}
				{selected && (
					<div className="mt-0.5" style={{ color: "var(--accent)" }}>
						&#10003; 已选中
					</div>
				)}
				<div className="mt-1 flex items-center gap-2">
					{isSelectable && (
						<button
							type="button"
							className="hover:underline"
							style={{ color: "var(--accent)" }}
							aria-pressed={selected}
							onClick={(event) => {
								event.stopPropagation();
								onSelect?.(asset.name, event);
							}}
						>
							{selected ? "取消选择" : "选择"}
						</button>
					)}
					{onDelete && (
						<button
							type="button"
							className="hover:underline"
							style={{ color: "var(--danger)" }}
							onClick={(event) => {
								event.stopPropagation();
								onDelete(asset.name);
							}}
						>
							删除
						</button>
					)}
				</div>
			</div>
		</div>
	);
}
