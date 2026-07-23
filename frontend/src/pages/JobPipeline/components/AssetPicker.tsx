import { useEffect, useMemo, useState } from "react";
import { listIndexedAssets } from "../../../api/assets";
import type { AssetRecord } from "../../../types/asset";

interface AssetPickerProps {
	projectId: string;
	product?: string;
	preferredCategory?: string;
	onSelect: (asset: AssetRecord) => void;
	onCancel: () => void;
}

export default function AssetPicker({
	projectId,
	product,
	preferredCategory,
	onSelect,
	onCancel,
}: AssetPickerProps) {
	const [assets, setAssets] = useState<AssetRecord[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState("");
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [categoryFilter, setCategoryFilter] = useState(
		preferredCategory ?? "",
	);

	useEffect(() => {
		setLoading(true);
		listIndexedAssets(projectId, product ? { product } : undefined)
			.then((res) => {
				setAssets(res.assets.filter((a) => a.status === "available"));
				setError("");
			})
			.catch((e) => {
				console.error("load indexed assets failed", e);
				setError("加载素材库失败");
			})
			.finally(() => setLoading(false));
	}, [projectId, product]);

	const categories = useMemo(() => {
		const set = new Set(assets.map((a) => a.category).filter(Boolean));
		return ["", ...Array.from(set).sort()];
	}, [assets]);

	const filteredAssets = useMemo(() => {
		if (!categoryFilter) return assets;
		return assets.filter((a) => a.category === categoryFilter);
	}, [assets, categoryFilter]);

	const selectedAsset = assets.find((a) => a.asset_id === selectedId);

	return (
		<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
			<div className="bg-white rounded-lg shadow-xl p-4 max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
				<div className="flex items-center justify-between mb-3">
					<h4 className="text-base font-semibold text-[var(--text-primary)]">
						从素材库选择
					</h4>
					<button
						type="button"
						className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] text-sm"
						onClick={onCancel}
					>
						取消
					</button>
				</div>

				<div className="flex items-center gap-2 mb-3">
					<label className="text-xs text-[var(--text-secondary)]">分类：</label>
					<select
						className="text-xs border border-[var(--border-default)] rounded px-2 py-1 bg-white"
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

				<div className="overflow-y-auto flex-1 grid grid-cols-2 gap-2 min-h-0">
					{filteredAssets.map((asset) => {
						const isSelected = selectedId === asset.asset_id;
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
								<div className="h-24 bg-[var(--bg-page)] flex items-center justify-center overflow-hidden">
									<img
										src={`/api/assets/${asset.asset_id}/thumbnail`}
										alt={asset.asset_id}
										className="w-full h-full object-cover"
										loading="lazy"
										onError={(e) => {
											e.currentTarget.style.display = "none";
										}}
									/>
								</div>
								<div className="p-2">
									<p className="text-xs font-medium truncate">
										{asset.asset_id}
									</p>
									<p className="text-xs text-[var(--text-tertiary)]">
										{asset.category} · {asset.duration_seconds.toFixed(1)}s
									</p>
								</div>
							</button>
						);
					})}
				</div>

				<div className="flex justify-end gap-2 mt-4 pt-3 border-t border-[var(--border-default)]">
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
