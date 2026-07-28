import { useEffect, useMemo, useState } from "react";
import { listIndexedAssetsShared } from "../../../api/assetLibrary";
import type { AssetRecord } from "../../../types/asset";
import { resolveAssetMediaUrl } from "../../../utils/assetMedia";

interface AssetPickerProps {
	product?: string;
	preferredCategory?: string;
	onSelect: (asset: AssetRecord) => void;
	onCancel: () => void;
}

export default function AssetPicker({
	product,
	preferredCategory,
	onSelect,
	onCancel,
}: AssetPickerProps) {
	const [assets, setAssets] = useState<AssetRecord[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState("");
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [categoryFilter, setCategoryFilter] = useState(preferredCategory ?? "");

	useEffect(() => {
		setLoading(true);
		listIndexedAssetsShared(product ? { product } : undefined)
			.then((res) => {
				setAssets(res.assets.filter((a) => a.status === "available"));
				setError("");
			})
			.catch((e) => {
				console.error("load indexed assets failed", e);
				setError("加载素材库失败");
			})
			.finally(() => setLoading(false));
	}, [product]);

	const categories = useMemo(() => {
		const set = new Set(assets.map((a) => a.category).filter(Boolean));
		return ["", ...Array.from(set).sort()];
	}, [assets]);

	const filteredAssets = useMemo(() => {
		if (!categoryFilter) return assets;
		return assets.filter((a) => a.category === categoryFilter);
	}, [assets, categoryFilter]);

	const selectedAsset = assets.find((a) => a.asset_id === selectedId);

	function formatDuration(seconds: number) {
		const minute = Math.floor(seconds / 60);
		const second = String(Math.floor(seconds % 60)).padStart(2, "0");
		return `${minute}:${second}`;
	}

	function formatConfidence(confidence: number) {
		return `${Math.round(confidence * 100)}%`;
	}

	return (
		<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
			<div className="bg-[var(--bg-card)] rounded-lg shadow-xl max-w-5xl w-full max-h-[85vh] flex flex-col">
				<div className="flex items-center justify-between p-4 border-b border-[var(--border-default)]">
					<div>
						<h4 className="text-base font-semibold text-[var(--text-primary)]">
							选择库内素材
						</h4>
						<p className="text-xs text-[var(--text-tertiary)] mt-0.5">
							点击素材可在右侧预览，确认后替换当前句素材
						</p>
					</div>
					<button
						type="button"
						className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] text-sm"
						onClick={onCancel}
					>
						取消
					</button>
				</div>

				<div className="flex flex-col md:flex-row flex-1 min-h-0">
					{/* Left: asset list */}
					<div className="flex-1 min-w-0 flex flex-col border-b md:border-b-0 md:border-r border-[var(--border-default)]">
						<div className="flex items-center gap-2 p-3 border-b border-[var(--border-default)]">
							<label className="text-xs text-[var(--text-secondary)]">
								分类：
							</label>
							<select
								className="text-xs border border-[var(--border-default)] rounded px-2 py-1 bg-[var(--bg-card)]"
								value={categoryFilter}
								onChange={(e) => setCategoryFilter(e.target.value)}
							>
								<option value="">全部</option>
								{categories.map((c) => (
									<option key={c} value={c}>
										{c}
									</option>
								))}
							</select>
							<span className="text-xs text-[var(--text-tertiary)] ml-2">
								共 {filteredAssets.length} 个素材
							</span>
						</div>

						<div className="overflow-y-auto flex-1 p-3">
							{loading && (
								<p className="text-sm text-[var(--text-tertiary)] py-8 text-center">
									加载中…
								</p>
							)}
							{!loading && error && (
								<p className="text-sm text-[var(--alert-red)] py-8 text-center">
									{error}
								</p>
							)}
							{!loading && !error && filteredAssets.length === 0 && (
								<p className="text-sm text-[var(--text-tertiary)] py-8 text-center">
									没有可用手动选择的素材。
								</p>
							)}
							<div className="grid grid-cols-2 gap-2">
								{filteredAssets.map((asset) => {
									const isSelected = selectedId === asset.asset_id;
									const fileName =
										asset.file_path.split("/").pop() || asset.asset_id;
									return (
										<button
											key={asset.asset_id}
											type="button"
											className={`text-left border rounded-lg overflow-hidden transition-all ${
												isSelected
													? "border-[var(--btn-primary-bg)] ring-1 ring-[var(--btn-primary-bg)]"
													: "border-[var(--border-default)] hover:border-[var(--text-secondary)]"
											}`}
											onClick={() => setSelectedId(asset.asset_id)}
										>
											<div className="h-28 bg-[var(--bg-page)] flex items-center justify-center overflow-hidden">
												<img
													src={`/api/assets/${asset.asset_id}/thumbnail`}
													alt={fileName}
													className="w-full h-full object-cover"
													loading="lazy"
													onError={(e) => {
														e.currentTarget.style.display = "none";
													}}
												/>
											</div>
											<div className="p-2">
												<p
													className="text-xs font-medium truncate"
													title={fileName}
												>
													{fileName}
												</p>
												<p className="text-xs text-[var(--text-tertiary)]">
													{asset.category} ·{" "}
													{formatDuration(asset.duration_seconds)}
												</p>
											</div>
										</button>
									);
								})}
							</div>
						</div>
					</div>

					{/* Right: preview */}
					<div className="w-full md:w-96 flex-shrink-0 p-4 bg-[var(--bg-page)] overflow-y-auto">
						{selectedAsset ? (
							<div className="space-y-4">
								<div className="rounded-lg bg-black overflow-hidden">
									<video
										key={selectedAsset.asset_id}
										controls={true}
										className="w-full rounded-lg max-h-64"
										preload="metadata"
									>
										<source
											src={resolveAssetMediaUrl(selectedAsset.file_path)}
										/>
										您的浏览器不支持视频播放
									</video>
								</div>
								<div className="space-y-2 text-sm">
									<div className="flex justify-between">
										<span className="text-[var(--text-secondary)]">ID</span>
										<span className="text-[var(--text-primary)] break-all text-right max-w-[70%]">
											{selectedAsset.asset_id}
										</span>
									</div>
									<div className="flex justify-between">
										<span className="text-[var(--text-secondary)]">分类</span>
										<span className="text-[var(--text-primary)]">
											{selectedAsset.category}
										</span>
									</div>
									<div className="flex justify-between">
										<span className="text-[var(--text-secondary)]">时长</span>
										<span className="text-[var(--text-primary)]">
											{formatDuration(selectedAsset.duration_seconds)}
										</span>
									</div>
									<div className="flex justify-between">
										<span className="text-[var(--text-secondary)]">置信度</span>
										<span className="text-[var(--text-primary)]">
											{formatConfidence(selectedAsset.confidence)}
										</span>
									</div>
								</div>
							</div>
						) : (
							<div className="h-full flex flex-col items-center justify-center text-center py-12 text-[var(--text-tertiary)]">
								<div className="text-3xl mb-2">{"🎬"}</div>
								<p className="text-sm">点击左侧素材</p>
								<p className="text-xs mt-1">在右侧预览并确认选择</p>
							</div>
						)}
					</div>
				</div>

				<div className="flex justify-end gap-2 p-4 border-t border-[var(--border-default)]">
					<button
						type="button"
						className="px-4 py-2 rounded-md text-xs border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]"
						onClick={onCancel}
					>
						取消
					</button>
					<button
						type="button"
						className="px-4 py-2 rounded-md text-xs bg-[var(--btn-primary-bg)] text-white hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed"
						onClick={() => selectedAsset && onSelect(selectedAsset)}
						disabled={!selectedAsset}
					>
						确认选择
					</button>
				</div>
			</div>
		</div>
	);
}
