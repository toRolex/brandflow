import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { DEFAULT_PAGE_SIZE } from "../api/core";
import AssetGrid from "../components/AssetGrid";
import AssetPreviewPanel from "../components/AssetPreviewPanel";
import AssetUploadZone from "../components/AssetUploadZone";
import BatchActionBar from "../components/BatchActionBar";
import ConfirmDialog from "../components/ConfirmDialog";
import IndexProgress from "../components/IndexProgress";
import Pagination from "../components/Pagination";
import { useProducts } from "../ProductContext";
import type {
	AssetCategory,
	AssetFilters,
	AssetRecord,
	AssetStats,
	CategoryItem,
	IndexStatus,
} from "../types";

const STATUS_OPTIONS = [
	"available",
	"disabled",
	"pending_review",
	"classification_failed",
] as const;

const STATUS_LABELS: Record<string, string> = {
	available: "可用",
	disabled: "已禁用",
	pending_review: "待审核",
};

const DEFAULT_FILTERS: AssetFilters = {
	product: "",
	category: "",
	status: "",
	keyword: "",
	durationMin: 0,
	durationMax: 0,
	confidenceMin: 0,
	confidenceMax: 1,
	usageMin: 0,
	usageMax: 0,
};

const DEFAULT_STATS: AssetStats = {
	total: 0,
	available: 0,
	disabled: 0,
	source_videos: 0,
	category_counts: {},
	duration_min: 0,
	duration_max: 0,
	usage_min: 0,
	usage_max: 0,
};

export default function SmartAssetLibrary() {
	const [assets, setAssets] = useState<AssetRecord[]>([]);
	const [stats, setStats] = useState<AssetStats>(DEFAULT_STATS);
	const [filters, setFilters] = useState<AssetFilters>(DEFAULT_FILTERS);
	const [showAdvanced, setShowAdvanced] = useState(false);
	const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
	const [previewAsset, setPreviewAsset] = useState<AssetRecord | null>(null);

	const [indexStatus, setIndexStatus] = useState<IndexStatus>("idle");
	const [indexStep, setIndexStep] = useState("cut");
	const [indexProgress, setIndexProgress] = useState(0);
	const [indexCurrent, setIndexCurrent] = useState(0);
	const [indexTotal, setIndexTotal] = useState(0);
	const [indexTaskId, setIndexTaskId] = useState<string | null>(null);

	const [isBatchUpdating, setIsBatchUpdating] = useState(false);
	const [isPreviewUpdating, setIsPreviewUpdating] = useState(false);
	const [confirmDelete, setConfirmDelete] = useState<{
		assetId?: string;
		batchCount?: number;
	} | null>(null);

	const [page, setPage] = useState(1);
	const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
	const [total, setTotal] = useState(0);
	const requestIdRef = useRef(0);

	const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

	const { products, activeProductName } = useProducts();

	const [configuredCategories, setConfiguredCategories] = useState<
		CategoryItem[]
	>([]);

	// Initialize filters from active product once, avoiding a second request.
	useEffect(() => {
		if (activeProductName && !filters.product) {
			setFilters((f) => ({ ...f, product: activeProductName }));
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [activeProductName]);

	const loadCategories = useCallback(async () => {
		try {
			const cats = await api.listCategories();
			setConfiguredCategories(cats);
		} catch {
			setConfiguredCategories([]);
		}
	}, []);

	useEffect(() => {
		void loadCategories();
	}, [loadCategories]);

	const loadAssets = useCallback(async () => {
		const requestId = ++requestIdRef.current;
		const params: Parameters<typeof api.listIndexedAssetsShared>[0] = {
			page,
			pageSize,
		};
		if (filters.product) params.product = filters.product;
		if (filters.category) params.category = filters.category;
		if (filters.status) params.status = filters.status;
		if (filters.keyword.trim()) params.q = filters.keyword.trim();
		if (filters.durationMin > 0) params.durationMin = filters.durationMin;
		if (filters.durationMax > 0) params.durationMax = filters.durationMax;
		if (filters.confidenceMin > 0) params.confidenceMin = filters.confidenceMin;
		if (filters.confidenceMax < 1) params.confidenceMax = filters.confidenceMax;
		if (filters.usageMin > 0) params.usageMin = filters.usageMin;
		if (filters.usageMax > 0) params.usageMax = filters.usageMax;

		try {
			const res = await api.listIndexedAssetsShared(params);
			if (requestId !== requestIdRef.current) return;
			const lastPage = Math.max(1, Math.ceil(res.total / pageSize));
			if (page > lastPage) {
				setPage(lastPage);
				return;
			}
			setAssets(res.assets);
			setStats(res.stats);
			setTotal(res.total);
		} catch (error) {
			if (requestId !== requestIdRef.current) return;
			console.error("load assets failed", error);
		}
	}, [filters, page, pageSize]);

	useEffect(() => {
		void loadAssets();
	}, [loadAssets]);

	// Reset pagination when filters change.
	useEffect(() => {
		setPage(1);
	}, [
		filters.product,
		filters.category,
		filters.status,
		filters.keyword,
		filters.durationMin,
		filters.durationMax,
		filters.confidenceMin,
		filters.confidenceMax,
		filters.usageMin,
		filters.usageMax,
	]);

	const categoryCounts = useMemo(() => {
		const counts = new Map<string, number>();
		for (const cat of configuredCategories) {
			counts.set(cat.name, 0);
		}
		for (const [cat, n] of Object.entries(stats.category_counts)) {
			counts.set(cat, (counts.get(cat) || 0) + n);
		}
		return counts;
	}, [stats.category_counts, configuredCategories]);

	const unmappedCategoryNames = useMemo(() => {
		const configuredNames = new Set(configuredCategories.map((c) => c.name));
		const found = new Set<string>();
		for (const cat of Object.keys(stats.category_counts)) {
			if (cat && !configuredNames.has(cat)) {
				found.add(cat);
			}
		}
		return Array.from(found).sort();
	}, [stats.category_counts, configuredCategories]);

	const durationRange = useMemo(() => {
		if (stats.duration_max === 0) return { min: 0, max: 0 };
		return {
			min: Math.floor(stats.duration_min * 10) / 10,
			max: Math.ceil(stats.duration_max * 10) / 10,
		};
	}, [stats.duration_min, stats.duration_max]);

	const usageRange = useMemo(() => {
		if (stats.usage_max === 0) return { min: 0, max: 0 };
		return { min: stats.usage_min, max: stats.usage_max };
	}, [stats.usage_min, stats.usage_max]);

	const toggleSelect = useCallback((assetId: string) => {
		setSelectedIds((prev) => {
			const next = new Set(prev);
			if (next.has(assetId)) {
				next.delete(assetId);
			} else {
				next.add(assetId);
			}
			return next;
		});
	}, []);

	const pollIndexProgress = useCallback(
		async (taskId: string) => {
			try {
				const status = await api.getIndexStatus(taskId);

				setIndexProgress(status.progress);
				setIndexStep(status.current_step);
				setIndexCurrent(status.current_video);
				setIndexTotal(status.total_videos);

				if (status.status === "completed") {
					setIndexStatus("done");
					setIndexStep("done");
					setIndexProgress(100);
					if (pollIntervalRef.current) {
						clearInterval(pollIntervalRef.current);
						pollIntervalRef.current = null;
					}
					await loadAssets();
					setTimeout(() => {
						setIndexStatus("idle");
						setIndexTaskId(null);
					}, 2000);
				} else if (status.status === "failed") {
					setIndexStatus("idle");
					setIndexTaskId(null);
					if (pollIntervalRef.current) {
						clearInterval(pollIntervalRef.current);
						pollIntervalRef.current = null;
					}
					const errorMsg = status.error || "未知错误";
					console.error("Index failed:", errorMsg);
					alert(
						`素材入库失败：${errorMsg}\n\n请检查服务器终端日志获取详细信息。`,
					);
				}
			} catch (error) {
				console.error("Poll failed:", error);
			}
		},
		[loadAssets],
	);

	const handleUploadConfirm = useCallback(
		async (files: File[]) => {
			if (files.length === 0) {
				return;
			}

			setIndexStatus("processing");
			setIndexStep("cut");
			setIndexProgress(0);
			setIndexCurrent(0);
			setIndexTotal(files.length);

			try {
				for (const file of files) {
					await api.uploadAssetShared(file);
				}

				const fileNames = files.map((f) => f.name);
				const result = await api.indexAssetsSharedAsync(fileNames);

				if (!result.task_id) {
					await loadAssets();
					setIndexStatus("idle");
					return;
				}

				setIndexTaskId(result.task_id);

				pollIntervalRef.current = setInterval(() => {
					pollIndexProgress(result.task_id);
				}, 1000);

				await pollIndexProgress(result.task_id);
			} catch (error) {
				setIndexStatus("idle");
				if (pollIntervalRef.current) {
					clearInterval(pollIntervalRef.current);
					pollIntervalRef.current = null;
				}
				throw error;
			}
		},
		[loadAssets, pollIndexProgress],
	);

	useEffect(
		() => () => {
			if (pollIntervalRef.current) {
				clearInterval(pollIntervalRef.current);
			}
		},
		[],
	);

	const handleBatchUpdate = useCallback(
		async (status: "available" | "disabled") => {
			if (selectedIds.size === 0 || isBatchUpdating) {
				return;
			}

			setIsBatchUpdating(true);
			try {
				await api.updateAssetStatusShared(Array.from(selectedIds), status);
				setSelectedIds(new Set());
				await loadAssets();
			} finally {
				setIsBatchUpdating(false);
			}
		},
		[isBatchUpdating, loadAssets, selectedIds],
	);

	const handleBatchEdit = useCallback(
		async (fields: { product?: string; category?: string }) => {
			if (selectedIds.size === 0 || isBatchUpdating) {
				return;
			}

			setIsBatchUpdating(true);
			try {
				await api.batchUpdateAssetFields(Array.from(selectedIds), fields);
				setSelectedIds(new Set());
				await loadAssets();
			} finally {
				setIsBatchUpdating(false);
			}
		},
		[isBatchUpdating, loadAssets, selectedIds],
	);

	const configuredCategoryNames = useMemo(
		() => configuredCategories.map((c) => c.name),
		[configuredCategories],
	);

	const hasUnmappedInSelection = useMemo(() => {
		const configuredNames = new Set(configuredCategoryNames);
		for (const id of selectedIds) {
			const asset = assets.find((a) => a.asset_id === id);
			if (asset && !configuredNames.has(asset.category)) {
				return true;
			}
		}
		return false;
	}, [selectedIds, assets, configuredCategoryNames]);

	const handleBatchReclassify = useCallback(
		async (category: string) => {
			if (selectedIds.size === 0 || isBatchUpdating) {
				return;
			}

			setIsBatchUpdating(true);
			try {
				await api.batchReclassifyAssets(Array.from(selectedIds), category);
				setSelectedIds(new Set());
				await loadAssets();
				await loadCategories();
			} finally {
				setIsBatchUpdating(false);
			}
		},
		[isBatchUpdating, loadAssets, loadCategories, selectedIds],
	);

	const handleDelete = useCallback((assetId: string) => {
		setConfirmDelete({ assetId });
	}, []);

	const handleBatchDelete = useCallback(() => {
		if (selectedIds.size === 0 || isBatchUpdating) {
			return;
		}
		setConfirmDelete({ batchCount: selectedIds.size });
	}, [selectedIds.size, isBatchUpdating]);

	const executeDelete = useCallback(async () => {
		if (!confirmDelete) return;
		if (confirmDelete.assetId) {
			const assetId = confirmDelete.assetId;
			setConfirmDelete(null);
			try {
				await api.deleteAssetShared(assetId);
				await loadAssets();
			} catch (error) {
				console.error("delete asset failed", error);
			}
		} else if (confirmDelete.batchCount) {
			setConfirmDelete(null);
			setIsBatchUpdating(true);
			try {
				await api.batchDeleteAssets(Array.from(selectedIds));
				setSelectedIds(new Set());
				await loadAssets();
			} catch (error) {
				console.error("batch delete failed", error);
			} finally {
				setIsBatchUpdating(false);
			}
		}
	}, [confirmDelete, assets, loadAssets, selectedIds]);

	const handlePreviewStatusToggle = useCallback(
		async (asset: AssetRecord, nextStatus: AssetRecord["status"]) => {
			if (isPreviewUpdating) {
				return;
			}

			setIsPreviewUpdating(true);
			try {
				await api.updateAssetStatusShared([asset.asset_id], nextStatus);
				await loadAssets();
				setPreviewAsset((prev) => {
					if (!prev || prev.asset_id !== asset.asset_id) {
						return prev;
					}
					return { ...prev, status: nextStatus };
				});
			} finally {
				setIsPreviewUpdating(false);
			}
		},
		[isPreviewUpdating, loadAssets],
	);

	const handlePreviewFieldsUpdate = useCallback(
		async (
			asset: AssetRecord,
			fields: { product?: string; category?: string },
		) => {
			if (isPreviewUpdating) {
				return;
			}

			setIsPreviewUpdating(true);
			try {
				await api.updateAssetFields(asset.asset_id, fields);
				await loadAssets();
				setPreviewAsset((prev) => {
					if (!prev || prev.asset_id !== asset.asset_id) {
						return prev;
					}
					return {
						...prev,
						...(fields.product !== undefined && { product: fields.product }),
						...(fields.category !== undefined && {
							category: fields.category as AssetCategory,
						}),
					};
				});
			} finally {
				setIsPreviewUpdating(false);
			}
		},
		[isPreviewUpdating, loadAssets],
	);

	const handlePageChange = (p: number) => {
		setSelectedIds(new Set());
		setPage(p);
	};

	const handlePageSizeChange = (size: number) => {
		setSelectedIds(new Set());
		setPageSize(size);
		setPage(1);
	};

	return (
		<div className="space-y-4">
			<div className="grid grid-cols-2 md:grid-cols-4 gap-3">
				{[
					{
						label: "总切片",
						value: stats.total,
						baseStyle: {
							background: "var(--bg-card)",
							borderColor: "var(--border-default)",
						},
					},
					{
						label: "可用",
						value: stats.available,
						baseStyle: {
							background: "var(--bg-tag-green)",
							borderColor: "var(--text-tag-green)",
							color: "var(--text-tag-green)",
						},
					},
					{
						label: "已禁用",
						value: stats.disabled,
						baseStyle: {
							background: "var(--alert-red-muted)",
							borderColor: "var(--alert-red)",
							color: "var(--alert-red)",
						},
					},
					{
						label: "源视频",
						value: stats.source_videos,
						baseStyle: {
							background: "var(--bg-card)",
							borderColor: "var(--border-default)",
						},
					},
				].map((item) => (
					<div
						key={item.label}
						className="rounded-lg border p-3 text-center"
						style={item.baseStyle}
					>
						<p className="text-lg font-semibold">{item.value}</p>
						<p className="text-xs" style={{ color: "var(--text-secondary)" }}>
							{item.label}
						</p>
					</div>
				))}
			</div>

			<AssetUploadZone
				onConfirm={handleUploadConfirm}
				disabled={indexStatus === "processing"}
			/>

			{indexStatus !== "idle" && (
				<IndexProgress
					step={indexStep}
					progress={indexProgress}
					current={indexCurrent}
					total={indexTotal}
					skippedCount={Math.max(stats.total - indexCurrent, 0)}
					taskId={indexTaskId}
					isRunning={indexStatus === "processing"}
				/>
			)}

			<div className="space-y-2">
				<div className="flex flex-wrap gap-2 items-center">
					<select
						className="border rounded-md px-3 py-2 text-sm"
						style={{
							background: "var(--bg-card)",
							color: "var(--text-primary)",
						}}
						value={filters.product}
						onChange={(e) =>
							setFilters((f) => ({
								...f,
								product: e.target.value,
								category: "",
							}))
						}
					>
						<option value="">全部产品</option>
						{products.map((p) => (
							<option key={p.id} value={p.name || p.id}>
								{p.name || p.id}
							</option>
						))}
					</select>

					<select
						className="border rounded-md px-3 py-2 text-sm"
						style={{
							background: "var(--bg-card)",
							color: "var(--text-primary)",
						}}
						value={filters.category}
						onChange={(e) =>
							setFilters((f) => ({ ...f, category: e.target.value }))
						}
					>
						<option value="">全部分类 ({total})</option>
						{configuredCategories.map((cat) => (
							<option key={cat.id} value={cat.name}>
								{cat.name} ({categoryCounts.get(cat.name) ?? 0})
							</option>
						))}
						{unmappedCategoryNames.length > 0 && (
							<>
								<option disabled={true}>── 未映射/历史分类 ──</option>
								{unmappedCategoryNames.map((cat) => (
									<option key={cat} value={cat}>
										{cat} ({categoryCounts.get(cat) ?? 0})
									</option>
								))}
							</>
						)}
					</select>

					<select
						className="border rounded-md px-3 py-2 text-sm"
						style={{
							background: "var(--bg-card)",
							color: "var(--text-primary)",
						}}
						value={filters.status}
						onChange={(e) =>
							setFilters((f) => ({ ...f, status: e.target.value }))
						}
					>
						<option value="">全部状态</option>
						{STATUS_OPTIONS.map((s) => (
							<option key={s} value={s}>
								{STATUS_LABELS[s]}
							</option>
						))}
					</select>

					{durationRange.max > 0 && (
						<div
							className="flex items-center gap-1.5 text-sm"
							style={{ color: "var(--text-secondary)" }}
						>
							<span>时长</span>
							<input
								type="range"
								className="w-20"
								style={{ accentColor: "var(--accent)" }}
								min={durationRange.min}
								max={durationRange.max}
								step={0.1}
								value={filters.durationMin}
								onChange={(e) =>
									setFilters((f) => ({
										...f,
										durationMin: Math.min(
											Number(e.target.value),
											f.durationMax === 0 ? durationRange.max : f.durationMax,
										),
									}))
								}
							/>
							<span>{filters.durationMin.toFixed(1)}s</span>
							<span>~</span>
							<input
								type="range"
								className="w-20"
								style={{ accentColor: "var(--accent)" }}
								min={durationRange.min}
								max={durationRange.max}
								step={0.1}
								value={
									filters.durationMax === 0
										? durationRange.max
										: filters.durationMax
								}
								onChange={(e) =>
									setFilters((f) => ({
										...f,
										durationMax: Math.max(
											Number(e.target.value),
											f.durationMin,
										),
									}))
								}
							/>
							<span>
								{(filters.durationMax === 0
									? durationRange.max
									: filters.durationMax
								).toFixed(1)}
								s
							</span>
						</div>
					)}

					<button
						className="text-sm px-2 py-1"
						style={{ color: "var(--accent)" }}
						onClick={() => setShowAdvanced((v) => !v)}
					>
						{showAdvanced ? "收起筛选 ▲" : "更多筛选 ▼"}
					</button>

					<button
						className="text-sm px-2 py-1 border rounded"
						style={{
							color: "var(--text-secondary)",
							borderColor: "var(--border-default)",
						}}
						onClick={() => setFilters(DEFAULT_FILTERS)}
					>
						清除筛选
					</button>

					{total > 0 && (
						<span
							className="text-xs ml-auto"
							style={{ color: "var(--text-secondary)" }}
						>
							共 {total} 条素材
						</span>
					)}
				</div>

				<input
					className="w-full border rounded-md px-3 py-2 text-sm"
					style={{ background: "var(--bg-card)", color: "var(--text-primary)" }}
					value={filters.keyword}
					onChange={(e) =>
						setFilters((f) => ({ ...f, keyword: e.target.value }))
					}
					placeholder="搜索 file_path / 标签"
				/>

				{showAdvanced && (
					<div
						className="flex flex-wrap gap-4 items-center text-sm"
						style={{ color: "var(--text-secondary)" }}
					>
						<div className="flex items-center gap-1.5">
							<span>置信度</span>
							<input
								type="number"
								className="w-16 border rounded px-2 py-1 text-sm"
								style={{
									background: "var(--bg-card)",
									color: "var(--text-primary)",
								}}
								min={0}
								max={1}
								step={0.1}
								value={filters.confidenceMin}
								onChange={(e) =>
									setFilters((f) => ({
										...f,
										confidenceMin: Number(e.target.value),
									}))
								}
								onBlur={(e) => {
									const raw = Number(e.target.value);
									const v = Number.isNaN(raw)
										? 0
										: Math.max(0, Math.min(1, raw));
									setFilters((f) => ({
										...f,
										confidenceMin: v,
										confidenceMax: Math.max(v, f.confidenceMax),
									}));
								}}
							/>
							<span>~</span>
							<input
								type="number"
								className="w-16 border rounded px-2 py-1 text-sm"
								style={{
									background: "var(--bg-card)",
									color: "var(--text-primary)",
								}}
								min={0}
								max={1}
								step={0.1}
								value={filters.confidenceMax}
								onChange={(e) =>
									setFilters((f) => ({
										...f,
										confidenceMax: Number(e.target.value),
									}))
								}
								onBlur={(e) => {
									const raw = Number(e.target.value);
									const v = Number.isNaN(raw)
										? 1
										: Math.max(0, Math.min(1, raw));
									setFilters((f) => ({
										...f,
										confidenceMax: v,
										confidenceMin: Math.min(v, f.confidenceMin),
									}));
								}}
							/>
						</div>

						<div className="flex items-center gap-1.5">
							<span>使用次数</span>
							<input
								type="number"
								className="w-16 border rounded px-2 py-1 text-sm"
								style={{
									background: "var(--bg-card)",
									color: "var(--text-primary)",
								}}
								min={0}
								step={1}
								value={filters.usageMin}
								onChange={(e) =>
									setFilters((f) => ({
										...f,
										usageMin: Math.max(0, Number(e.target.value)),
									}))
								}
							/>
							<span>~</span>
							<input
								type="number"
								className="w-16 border rounded px-2 py-1 text-sm"
								style={{
									background: "var(--bg-card)",
									color: "var(--text-primary)",
								}}
								min={0}
								step={1}
								value={
									filters.usageMax === 0 ? usageRange.max : filters.usageMax
								}
								onChange={(e) =>
									setFilters((f) => ({
										...f,
										usageMax: Math.max(0, Number(e.target.value)),
									}))
								}
							/>
						</div>
					</div>
				)}
			</div>

			{selectedIds.size > 0 && (
				<BatchActionBar
					count={selectedIds.size}
					onEnable={() => void handleBatchUpdate("available")}
					onDisable={() => void handleBatchUpdate("disabled")}
					onDelete={() => void handleBatchDelete()}
					onClear={() => setSelectedIds(new Set())}
					onBatchEdit={handleBatchEdit}
					onReclassify={handleBatchReclassify}
					categories={configuredCategoryNames}
					hasUnmappedReclassifyTargets={hasUnmappedInSelection}
				/>
			)}

			{assets.length > 0 && (
				<div className="flex items-center gap-3 text-sm">
					{selectedIds.size === assets.length ? (
						<button
							className="px-2 py-1 border rounded"
							style={{
								color: "var(--accent)",
								borderColor: "var(--border-default)",
							}}
							onClick={() => setSelectedIds(new Set())}
						>
							取消全选
						</button>
					) : (
						<button
							className="px-2 py-1 border rounded"
							style={{
								color: "var(--accent)",
								borderColor: "var(--border-default)",
							}}
							onClick={() =>
								setSelectedIds(new Set(assets.map((a) => a.asset_id)))
							}
						>
							全选当前页
						</button>
					)}
					{selectedIds.size > 0 && (
						<>
							<span style={{ color: "var(--text-secondary)" }}>
								已选 {selectedIds.size} 项
							</span>
							<button
								className="px-2 py-1 border rounded"
								style={{
									color: "var(--text-secondary)",
									borderColor: "var(--border-default)",
								}}
								onClick={() => setSelectedIds(new Set())}
							>
								清空选择
							</button>
						</>
					)}
				</div>
			)}

			<div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-4 items-start">
				{assets.length === 0 ? (
					<div
						className="flex flex-col items-center justify-center py-20"
						style={{ color: "var(--text-secondary)" }}
					>
						<p className="text-lg mb-2">没有符合筛选条件的素材</p>
						<p className="text-sm mb-4">试试调整筛选条件或清除所有筛选</p>
						<button
							className="px-4 py-2 text-sm border rounded-md"
							style={{
								color: "var(--text-secondary)",
								borderColor: "var(--border-default)",
							}}
							onClick={() => setFilters(DEFAULT_FILTERS)}
						>
							清除筛选
						</button>
					</div>
				) : (
					<AssetGrid
						assets={assets}
						selectedIds={selectedIds}
						onToggleSelect={toggleSelect}
						onPreview={setPreviewAsset}
						onDelete={handleDelete}
					/>
				)}

				<div className="xl:sticky xl:top-4">
					<AssetPreviewPanel
						asset={previewAsset}
						isUpdating={isPreviewUpdating}
						onToggleStatus={(asset, nextStatus) => {
							void handlePreviewStatusToggle(asset, nextStatus);
						}}
						onUpdateFields={handlePreviewFieldsUpdate}
						categories={configuredCategories.map((c) => c.name)}
					/>
				</div>
			</div>

			<Pagination
				page={page}
				pageSize={pageSize}
				total={total}
				onPageChange={handlePageChange}
				onPageSizeChange={handlePageSizeChange}
			/>

			<ConfirmDialog
				isOpen={confirmDelete !== null}
				title="确认删除"
				message={
					confirmDelete?.batchCount
						? `确认删除选中的 ${confirmDelete.batchCount} 个素材？此操作不可撤销。`
						: "确认删除此素材？此操作不可撤销。"
				}
				danger={true}
				confirmLabel="删除"
				onConfirm={executeDelete}
				onCancel={() => setConfirmDelete(null)}
			/>
		</div>
	);
}
