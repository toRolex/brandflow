import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { AssetCategory, AssetFilters, AssetRecord, AssetStats, CategoryItem, IndexStatus } from "../types";
import { useProducts } from "../ProductContext";
import AssetGrid from "../components/AssetGrid";
import AssetPreviewPanel from "../components/AssetPreviewPanel";
import AssetUploadZone from "../components/AssetUploadZone";
import IndexProgress from "../components/IndexProgress";
import BatchActionBar from "../components/BatchActionBar";
import ConfirmDialog from "../components/ConfirmDialog";

const STATUS_OPTIONS = ["available", "disabled", "pending_review", "classification_failed"] as const;

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

interface Props {
  projectId?: string;
}

const DEFAULT_STATS: AssetStats = {
  total: 0,
  available: 0,
  disabled: 0,
  source_videos: 0,
};

export default function SmartAssetLibrary({ projectId }: Props) {
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

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { products, activeProductName } = useProducts();

  const [configuredCategories, setConfiguredCategories] = useState<CategoryItem[]>([]);

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
    let res: { assets: AssetRecord[]; stats: AssetStats };
    const params: { product?: string } = {};
    if (filters.product) params.product = filters.product;
    if (projectId) {
      res = await api.listIndexedAssets(projectId, params);
    } else {
      res = await api.listIndexedAssetsShared(params);
    }
    setAssets(res.assets);
    setStats(res.stats);
  }, [projectId, filters.product]);

  useEffect(() => {
    void loadAssets();
  }, [loadAssets]);

  // Initialize product filter from active product context
  useEffect(() => {
    if (activeProductName && !filters.product) {
      setFilters((f) => ({ ...f, product: activeProductName }));
    }
  }, [activeProductName, filters.product]);

  const productFilteredAssets = useMemo(() => {
    if (!filters.product) return assets;
    return assets.filter((a) => a.product === filters.product);
  }, [assets, filters.product]);

  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    // Initialize all configured categories with 0
    for (const cat of configuredCategories) {
      counts.set(cat.name, 0);
    }
    // Count from product-filtered assets
    for (const asset of productFilteredAssets) {
      counts.set(asset.category, (counts.get(asset.category) || 0) + 1);
    }
    return counts;
  }, [productFilteredAssets, configuredCategories]);

  const durationRange = useMemo(() => {
    if (assets.length === 0) return { min: 0, max: 0 };
    const durations = assets.map((a) => a.duration_seconds);
    return {
      min: Math.floor(Math.min(...durations) * 10) / 10,
      max: Math.ceil(Math.max(...durations) * 10) / 10,
    };
  }, [assets]);

  const usageRange = useMemo(() => {
    if (assets.length === 0) return { min: 0, max: 0 };
    const counts = assets.map((a) => a.usage_count);
    return { min: Math.min(...counts), max: Math.max(...counts) };
  }, [assets]);

  const filteredAssets = useMemo(() => {
    const keywordLower = filters.keyword.trim().toLowerCase();

    return assets.filter((asset) => {
      if (filters.product && asset.product !== filters.product) {
        return false;
      }

      if (filters.category && asset.category !== filters.category) {
        return false;
      }

      if (filters.status && asset.status !== filters.status) {
        return false;
      }

      if (keywordLower) {
        const haystack = [asset.file_path, asset.tags]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(keywordLower)) {
          return false;
        }
      }

      if (filters.durationMax > 0 && asset.duration_seconds > filters.durationMax) {
        return false;
      }

      if (asset.duration_seconds < filters.durationMin) {
        return false;
      }

      if (asset.confidence < filters.confidenceMin) {
        return false;
      }

      if (asset.confidence > filters.confidenceMax) {
        return false;
      }

      if (filters.usageMax > 0 && asset.usage_count > filters.usageMax) {
        return false;
      }

      if (asset.usage_count < filters.usageMin) {
        return false;
      }

      return true;
    });
  }, [assets, filters]);

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
          alert(`素材入库失败：${errorMsg}\n\n请检查服务器终端日志获取详细信息。`);
        }
      } catch (error) {
        console.error("Poll failed:", error);
      }
    },
    [loadAssets]
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
          if (projectId) {
            await api.uploadAsset(projectId, file);
          } else {
            await api.uploadAssetShared(file);
          }
        }

        if (projectId) {
          await api.indexAssets(projectId);
          await loadAssets();
          setIndexStatus("done");
          setIndexStep("done");
          setIndexProgress(100);
          setTimeout(() => setIndexStatus("idle"), 2000);
        } else {
          const result = await api.indexAssetsSharedAsync();

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
        }
      } catch (error) {
        setIndexStatus("idle");
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
        throw error;
      }
    },
    [projectId, loadAssets, pollIndexProgress]
  );

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const handleBatchUpdate = useCallback(
    async (status: "available" | "disabled") => {
      if (selectedIds.size === 0 || isBatchUpdating) {
        return;
      }

      setIsBatchUpdating(true);
      try {
        if (projectId) {
          await api.updateAssetStatus(projectId, Array.from(selectedIds), status);
        } else {
          await api.updateAssetStatusShared(Array.from(selectedIds), status);
        }
        setSelectedIds(new Set());
        await loadAssets();
      } finally {
        setIsBatchUpdating(false);
      }
    },
    [isBatchUpdating, loadAssets, selectedIds, projectId]
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
    [isBatchUpdating, loadAssets, selectedIds]
  );

  const handleDelete = useCallback(
    (assetId: string) => {
      setConfirmDelete({ assetId });
    },
    []
  );

  const handleBatchDelete = useCallback(
    () => {
      if (selectedIds.size === 0 || isBatchUpdating) {
        return;
      }
      setConfirmDelete({ batchCount: selectedIds.size });
    },
    [selectedIds.size, isBatchUpdating]
  );

  const executeDelete = useCallback(async () => {
    if (!confirmDelete) return;
    if (confirmDelete.assetId) {
      const assetId = confirmDelete.assetId;
      setConfirmDelete(null);
      try {
        if (projectId) {
          const asset = assets.find((a) => a.asset_id === assetId);
          const name = asset?.file_path || assetId;
          await api.deleteAsset(projectId, name);
        } else {
          await api.deleteAssetShared(assetId);
        }
        await loadAssets();
      } catch (error) {
        console.error("delete asset failed", error);
      }
    } else if (confirmDelete.batchCount) {
      setConfirmDelete(null);
      setIsBatchUpdating(true);
      try {
        if (projectId) {
          for (const id of selectedIds) {
            const asset = assets.find((a) => a.asset_id === id);
            const name = asset?.file_path || id;
            await api.deleteAsset(projectId, name);
          }
        } else {
          await api.batchDeleteAssets(Array.from(selectedIds));
        }
        setSelectedIds(new Set());
        await loadAssets();
      } catch (error) {
        console.error("batch delete failed", error);
      } finally {
        setIsBatchUpdating(false);
      }
    }
  }, [confirmDelete, projectId, assets, loadAssets, selectedIds]);

  const handlePreviewStatusToggle = useCallback(
    async (asset: AssetRecord, nextStatus: AssetRecord["status"]) => {
      if (isPreviewUpdating) {
        return;
      }

      setIsPreviewUpdating(true);
      try {
        if (projectId) {
          await api.updateAssetStatus(projectId, [asset.asset_id], nextStatus);
        } else {
          await api.updateAssetStatusShared([asset.asset_id], nextStatus);
        }
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
    [isPreviewUpdating, loadAssets, projectId]
  );

  const handlePreviewFieldsUpdate = useCallback(
    async (asset: AssetRecord, fields: { product?: string; category?: string }) => {
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
            ...(fields.category !== undefined && { category: fields.category as AssetCategory }),
          };
        });
      } finally {
        setIsPreviewUpdating(false);
      }
    },
    [isPreviewUpdating, loadAssets]
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "总切片", value: stats.total, baseStyle: { background: "var(--bg-card)", borderColor: "var(--border-default)" } },
          { label: "可用", value: stats.available, baseStyle: { background: "var(--bg-tag-green)", borderColor: "var(--text-tag-green)", color: "var(--text-tag-green)" } },
          { label: "已禁用", value: stats.disabled, baseStyle: { background: "var(--alert-red-muted)", borderColor: "var(--alert-red)", color: "var(--alert-red)" } },
          { label: "源视频", value: stats.source_videos, baseStyle: { background: "var(--bg-card)", borderColor: "var(--border-default)" } },
        ].map((item) => (
          <div key={item.label} className="rounded-lg border p-3 text-center" style={item.baseStyle}>
            <p className="text-lg font-semibold">{item.value}</p>
            <p className="text-xs" style={{ color: "var(--text-secondary)" }}>{item.label}</p>
          </div>
        ))}
      </div>

      <AssetUploadZone onConfirm={handleUploadConfirm} disabled={indexStatus === "processing"} />

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
            style={{ background: "var(--bg-card)", color: "var(--text-primary)" }}
            value={filters.product}
            onChange={(e) => setFilters((f) => ({ ...f, product: e.target.value, category: "" }))}
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
            style={{ background: "var(--bg-card)", color: "var(--text-primary)" }}
            value={filters.category}
            onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}
          >
            <option value="">全部分类 ({stats.total})</option>
            {configuredCategories.map((cat) => (
              <option key={cat.id} value={cat.name}>
                {cat.name} ({categoryCounts.get(cat.name) ?? 0})
              </option>
            ))}
          </select>

          <select
            className="border rounded-md px-3 py-2 text-sm"
            style={{ background: "var(--bg-card)", color: "var(--text-primary)" }}
            value={filters.status}
            onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
          >
            <option value="">全部状态</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>

          {durationRange.max > 0 && (
            <div className="flex items-center gap-1.5 text-sm" style={{ color: "var(--text-secondary)" }}>
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
                    durationMin: Math.min(Number(e.target.value), f.durationMax === 0 ? durationRange.max : f.durationMax),
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
                value={filters.durationMax === 0 ? durationRange.max : filters.durationMax}
                onChange={(e) =>
                  setFilters((f) => ({
                    ...f,
                    durationMax: Math.max(Number(e.target.value), f.durationMin),
                  }))
                }
              />
              <span>{(filters.durationMax === 0 ? durationRange.max : filters.durationMax).toFixed(1)}s</span>
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
            style={{ color: "var(--text-secondary)", borderColor: "var(--border-default)" }}
            onClick={() => setFilters(DEFAULT_FILTERS)}
          >
            清除筛选
          </button>

          {filteredAssets.length !== assets.length && (
            <span className="text-xs ml-auto" style={{ color: "var(--text-secondary)" }}>
              共 {filteredAssets.length} / {assets.length} 条素材
            </span>
          )}
        </div>

        <input
          className="w-full border rounded-md px-3 py-2 text-sm"
          style={{ background: "var(--bg-card)", color: "var(--text-primary)" }}
          value={filters.keyword}
          onChange={(e) => setFilters((f) => ({ ...f, keyword: e.target.value }))}
          placeholder="搜索 file_path / 标签"
        />

        {showAdvanced && (
          <div className="flex flex-wrap gap-4 items-center text-sm" style={{ color: "var(--text-secondary)" }}>
            <div className="flex items-center gap-1.5">
              <span>置信度</span>
              <input
                type="number"
                className="w-16 border rounded px-2 py-1 text-sm"
                style={{ background: "var(--bg-card)", color: "var(--text-primary)" }}
                min={0}
                max={1}
                step={0.1}
                value={filters.confidenceMin}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, confidenceMin: Number(e.target.value) }))
                }
                onBlur={(e) => {
                  const raw = Number(e.target.value);
                  const v = Number.isNaN(raw) ? 0 : Math.max(0, Math.min(1, raw));
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
                style={{ background: "var(--bg-card)", color: "var(--text-primary)" }}
                min={0}
                max={1}
                step={0.1}
                value={filters.confidenceMax}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, confidenceMax: Number(e.target.value) }))
                }
                onBlur={(e) => {
                  const raw = Number(e.target.value);
                  const v = Number.isNaN(raw) ? 1 : Math.max(0, Math.min(1, raw));
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
                style={{ background: "var(--bg-card)", color: "var(--text-primary)" }}
                min={0}
                step={1}
                value={filters.usageMin}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, usageMin: Math.max(0, Number(e.target.value)) }))
                }
              />
              <span>~</span>
              <input
                type="number"
                className="w-16 border rounded px-2 py-1 text-sm"
                style={{ background: "var(--bg-card)", color: "var(--text-primary)" }}
                min={0}
                step={1}
                value={filters.usageMax === 0 ? usageRange.max : filters.usageMax}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, usageMax: Math.max(0, Number(e.target.value)) }))
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
          categories={configuredCategories.map((c) => c.name)}
        />
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-4 items-start">
        {filteredAssets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20" style={{ color: "var(--text-secondary)" }}>
            <p className="text-lg mb-2">没有符合筛选条件的素材</p>
            <p className="text-sm mb-4">试试调整筛选条件或清除所有筛选</p>
            <button
              className="px-4 py-2 text-sm border rounded-md"
              style={{ color: "var(--text-secondary)", borderColor: "var(--border-default)" }}
              onClick={() => setFilters(DEFAULT_FILTERS)}
            >
              清除筛选
            </button>
          </div>
        ) : (
          <AssetGrid
            assets={filteredAssets}
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
      <ConfirmDialog
        isOpen={confirmDelete !== null}
        title="确认删除"
        message={
          confirmDelete?.batchCount
            ? `确认删除选中的 ${confirmDelete.batchCount} 个素材？此操作不可撤销。`
            : "确认删除此素材？此操作不可撤销。"
        }
        danger
        confirmLabel="删除"
        onConfirm={executeDelete}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
