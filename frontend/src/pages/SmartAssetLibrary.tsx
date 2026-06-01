import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { AssetCategory, AssetRecord, AssetStats, IndexStatus } from "../types";
import AssetGrid from "../components/AssetGrid";
import AssetPreviewPanel from "../components/AssetPreviewPanel";
import AssetUploadZone from "../components/AssetUploadZone";
import IndexProgress from "../components/IndexProgress";
import BatchActionBar from "../components/BatchActionBar";

const CATEGORIES = [
  "产地溯源",
  "筛选分拣",
  "清洗泡发",
  "切配处理",
  "下锅入锅",
  "烹饪翻炒",
  "出锅装盘",
  "成品展示",
  "试吃品尝",
  "产品特写",
] as const;

interface Props {
  projectId: string;
  onUpload: (file: File) => Promise<void>;
}

const DEFAULT_STATS: AssetStats = {
  total: 0,
  available: 0,
  disabled: 0,
  source_videos: 0,
};

export default function SmartAssetLibrary({ projectId: _projectId, onUpload: _onUpload }: Props) {
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [stats, setStats] = useState<AssetStats>(DEFAULT_STATS);
  const [category, setCategory] = useState("");
  const [keyword, setKeyword] = useState("");
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

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAssets = useCallback(async () => {
    const res = await api.listIndexedAssetsShared();
    setAssets(res.assets);
    setStats(res.stats);
  }, []);

  useEffect(() => {
    void loadAssets();
  }, [loadAssets]);

  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const asset of assets) {
      counts.set(asset.category, (counts.get(asset.category) || 0) + 1);
    }
    return counts;
  }, [assets]);

  const filteredAssets = useMemo(() => {
    const keywordLower = keyword.trim().toLowerCase();

    return assets.filter((asset) => {
      if (category && asset.category !== category) {
        return false;
      }

      if (!keywordLower) {
        return true;
      }

      return [asset.file_path, asset.tags]
        .join(" ")
        .toLowerCase()
        .includes(keywordLower);
    });
  }, [assets, category, keyword]);

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
          console.error("Index failed:", status.error);
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
          await api.uploadAssetShared(file);
        }

        const result = await api.indexAssetsSharedAsync();
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
    [pollIndexProgress]
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
        await api.updateAssetStatusShared(Array.from(selectedIds), status);
        setSelectedIds(new Set());
        await loadAssets();
      } finally {
        setIsBatchUpdating(false);
      }
    },
    [isBatchUpdating, loadAssets, selectedIds]
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
    async (assetId: string) => {
      if (!window.confirm("确认删除此素材？此操作不可撤销。")) {
        return;
      }
      try {
        await api.deleteAssetShared(assetId);
        await loadAssets();
      } catch (error) {
        console.error("delete asset failed", error);
      }
    },
    [loadAssets]
  );

  const handleBatchDelete = useCallback(
    async () => {
      if (selectedIds.size === 0 || isBatchUpdating) {
        return;
      }

      const confirmed = window.confirm(
        `确认删除选中的 ${selectedIds.size} 个素材？此操作不可撤销。`
      );
      if (!confirmed) {
        return;
      }

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
    },
    [isBatchUpdating, loadAssets, selectedIds]
  );

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
    [isPreviewUpdating, loadAssets]
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
          { label: "总切片", value: stats.total, style: "bg-gray-50 border-gray-200" },
          { label: "可用", value: stats.available, style: "bg-green-50 border-green-200 text-green-700" },
          { label: "已禁用", value: stats.disabled, style: "bg-red-50 border-red-200 text-red-700" },
          { label: "源视频", value: stats.source_videos, style: "bg-gray-50 border-gray-200" },
        ].map((item) => (
          <div key={item.label} className={`rounded-lg border p-3 text-center ${item.style}`}>
            <p className="text-lg font-semibold">{item.value}</p>
            <p className="text-xs text-[#57606a]">{item.label}</p>
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

      <div className="flex gap-2 items-center">
        <select
          className="border rounded-md px-3 py-2 text-sm bg-white"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
        >
          <option value="">全部分类 ({stats.total})</option>
          {CATEGORIES.map((item) => (
            <option key={item} value={item}>
              {item} ({categoryCounts.get(item) || 0})
            </option>
          ))}
        </select>

        <input
          className="flex-1 border rounded-md px-3 py-2 text-sm"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜索 file_path / 标签"
        />
      </div>

      {selectedIds.size > 0 && (
        <BatchActionBar
          count={selectedIds.size}
          onEnable={() => void handleBatchUpdate("available")}
          onDisable={() => void handleBatchUpdate("disabled")}
          onDelete={() => void handleBatchDelete()}
          onClear={() => setSelectedIds(new Set())}
          onBatchEdit={handleBatchEdit}
        />
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-4 items-start">
        <AssetGrid
          assets={filteredAssets}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          onPreview={setPreviewAsset}
          onDelete={handleDelete}
        />

        <div className="xl:sticky xl:top-4">
          <AssetPreviewPanel
            asset={previewAsset}
            isUpdating={isPreviewUpdating}
            onToggleStatus={(asset, nextStatus) => {
              void handlePreviewStatusToggle(asset, nextStatus);
            }}
            onUpdateFields={handlePreviewFieldsUpdate}
          />
        </div>
      </div>
    </div>
  );
}
