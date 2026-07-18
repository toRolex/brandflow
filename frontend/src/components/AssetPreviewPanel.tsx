import { useState } from "react";
import type { AssetRecord } from "../types";

interface Props {
	asset: AssetRecord | null;
	isUpdating?: boolean;
	onToggleStatus?: (
		asset: AssetRecord,
		nextStatus: AssetRecord["status"],
	) => void;
	onUpdateFields?: (
		asset: AssetRecord,
		fields: { product?: string; category?: string },
	) => Promise<void>;
	categories?: string[];
}

function formatDuration(seconds: number) {
	const minute = Math.floor(seconds / 60);
	const second = String(Math.floor(seconds % 60)).padStart(2, "0");
	return `${minute}:${second}`;
}

function formatConfidence(confidence: number) {
	return `${Math.round(confidence * 100)}%`;
}

function formatDate(value: string) {
	if (!value) {
		return "-";
	}
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) {
		return value;
	}
	return date.toLocaleString("zh-CN", { hour12: false });
}

function resolveAssetMediaUrl(filePath: string) {
	if (!filePath) {
		return filePath;
	}

	const normalizedPath = filePath.replaceAll("\\", "/");
	if (normalizedPath.startsWith("/workspace/")) {
		return normalizedPath;
	}

	const workspaceIndex = normalizedPath.indexOf("/workspace/");
	if (workspaceIndex >= 0) {
		return normalizedPath.slice(workspaceIndex);
	}

	return normalizedPath;
}

function parseAssetTags(rawTags: unknown) {
	if (Array.isArray(rawTags)) {
		return rawTags.filter(
			(tag): tag is string => typeof tag === "string" && tag.trim().length > 0,
		);
	}

	if (typeof rawTags === "string") {
		const trimmed = rawTags.trim();
		if (!trimmed) {
			return [];
		}
		try {
			const parsed = JSON.parse(trimmed);
			if (Array.isArray(parsed)) {
				return parsed.filter(
					(tag): tag is string =>
						typeof tag === "string" && tag.trim().length > 0,
				);
			}
		} catch {
			return [trimmed];
		}
	}

	return [];
}

export default function AssetPreviewPanel({
	asset,
	isUpdating = false,
	onToggleStatus,
	onUpdateFields,
	categories = [],
}: Props) {
	const [isEditing, setIsEditing] = useState(false);
	const [editProduct, setEditProduct] = useState("");
	const [editCategory, setEditCategory] = useState("");
	const [isSaving, setIsSaving] = useState(false);

	if (!asset) {
		return (
			<section
				className="border rounded-lg p-6"
				style={{
					background: "var(--bg-card)",
					borderColor: "var(--border-default)",
				}}
			>
				<div className="text-sm" style={{ color: "var(--text-secondary)" }}>
					请选择素材以查看预览和元数据
				</div>
			</section>
		);
	}

	const isAvailable = asset.status === "available";
	const nextStatus: AssetRecord["status"] = isAvailable
		? "disabled"
		: "available";
	const mediaUrl = resolveAssetMediaUrl(asset.file_path);
	const tags = parseAssetTags(asset.tags as unknown);

	const handleStartEdit = () => {
		setEditProduct(asset.product);
		setEditCategory(asset.category);
		setIsEditing(true);
	};

	const handleCancelEdit = () => {
		setIsEditing(false);
	};

	const handleSaveEdit = async () => {
		if (!onUpdateFields) return;
		setIsSaving(true);
		try {
			await onUpdateFields(asset, {
				product: editProduct,
				category: editCategory,
			});
			setIsEditing(false);
		} finally {
			setIsSaving(false);
		}
	};

	return (
		<section
			className="border rounded-lg p-4 space-y-4"
			style={{
				background: "var(--bg-card)",
				borderColor: "var(--border-default)",
			}}
		>
			<div className="flex items-center justify-between">
				<div>
					<h3
						className="text-base font-semibold truncate"
						title={asset.asset_id}
						style={{ color: "var(--text-primary)" }}
					>
						素材预览
					</h3>
					<p
						className="text-xs mt-1 break-all"
						style={{ color: "var(--text-secondary)" }}
					>
						{asset.file_path}
					</p>
				</div>
				<div className="flex gap-2">
					{isEditing ? (
						<>
							<button
								type="button"
								className="text-xs px-3 py-1.5 rounded border border-[var(--success)] text-[var(--success)] hover:bg-[var(--success-bg)] disabled:opacity-50"
								onClick={handleSaveEdit}
								disabled={isSaving}
							>
								{isSaving ? "保存中..." : "保存"}
							</button>
							<button
								type="button"
								className="text-xs px-3 py-1.5 rounded border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-nav-active)]"
								onClick={handleCancelEdit}
								disabled={isSaving}
							>
								取消
							</button>
						</>
					) : (
						<>
							<button
								type="button"
								className="text-xs px-3 py-1.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--bg-nav-active)]"
								onClick={handleStartEdit}
								disabled={!onUpdateFields}
							>
								编辑
							</button>
							<button
								type="button"
								className={`text-xs px-3 py-1.5 rounded border transition-colors ${
									isAvailable
										? "border-[var(--danger)] text-[var(--danger)] hover:bg-[var(--danger-bg)]"
										: "border-[var(--success)] text-[var(--success)] hover:bg-[var(--success-bg)]"
								} disabled:opacity-50 disabled:cursor-not-allowed`}
								onClick={() => onToggleStatus?.(asset, nextStatus)}
								disabled={isUpdating || !onToggleStatus}
							>
								{isAvailable ? "禁用素材" : "启用素材"}
							</button>
						</>
					)}
				</div>
			</div>

			<div className="rounded-lg bg-black overflow-hidden">
				<video
					key={asset.asset_id}
					controls
					className="w-full max-h-[360px]"
					preload="metadata"
				>
					<source src={mediaUrl} />
					您的浏览器不支持视频播放
				</video>
			</div>

			<div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
				<div style={{ color: "var(--text-secondary)" }}>分类</div>
				<div>
					{isEditing ? (
						<select
							className="border rounded px-2 py-1 text-sm w-full"
							value={editCategory}
							onChange={(e) => setEditCategory(e.target.value)}
						>
							{categories.map((cat) => (
								<option key={cat} value={cat}>
									{cat}
								</option>
							))}
						</select>
					) : (
						asset.category
					)}
				</div>

				<div style={{ color: "var(--text-secondary)" }}>产品</div>
				<div>
					{isEditing ? (
						<input
							type="text"
							className="border rounded px-2 py-1 text-sm w-full"
							value={editProduct}
							onChange={(e) => setEditProduct(e.target.value)}
							placeholder="输入产品名称"
						/>
					) : (
						asset.product
					)}
				</div>

				<div style={{ color: "var(--text-secondary)" }}>置信度</div>
				<div>{formatConfidence(asset.confidence)}</div>

				<div style={{ color: "var(--text-secondary)" }}>时长</div>
				<div>{formatDuration(asset.duration_seconds)}</div>

				<div style={{ color: "var(--text-secondary)" }}>状态</div>
				<div>
					<span
						className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
							isAvailable ? "badge-success" : "badge-danger"
						}`}
						style={
							isAvailable
								? {
										background: "var(--badge-success-bg)",
										color: "var(--badge-success-text)",
									}
								: {
										background: "var(--badge-danger-bg)",
										color: "var(--badge-danger-text)",
									}
						}
					>
						{isAvailable ? "可用" : "已禁用"}
					</span>
				</div>

				<div style={{ color: "var(--text-secondary)" }}>使用次数</div>
				<div>{asset.usage_count}</div>

				<div style={{ color: "var(--text-secondary)" }}>来源视频</div>
				<div className="break-all">{asset.source_video}</div>

				<div style={{ color: "var(--text-secondary)" }}>创建时间</div>
				<div>{formatDate(asset.created_at)}</div>

				<div style={{ color: "var(--text-secondary)" }}>最近使用</div>
				<div>{formatDate(asset.last_used_at)}</div>
			</div>

			<div>
				<div
					className="text-xs mb-2"
					style={{ color: "var(--text-secondary)" }}
				>
					标签
				</div>
				<div className="flex flex-wrap gap-2">
					{tags.length > 0 ? (
						tags.map((tag) => (
							<span
								key={tag}
								className="px-2 py-0.5 rounded-full text-xs"
								style={{
									background: "var(--badge-default-bg)",
									color: "var(--badge-default-text)",
								}}
							>
								{tag}
							</span>
						))
					) : (
						<span className="text-sm" style={{ color: "var(--text-tertiary)" }}>
							暂无标签
						</span>
					)}
				</div>
			</div>
		</section>
	);
}
