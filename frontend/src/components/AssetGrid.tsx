import { useCallback, useRef } from "react";
import type { AssetRecord } from "../types";
import AssetCard from "./AssetCard";

interface Props {
  assets: AssetRecord[];
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onPreview: (asset: AssetRecord) => void;
  onDelete?: (assetId: string) => void;
}

export default function AssetGrid({ assets, selectedIds, onToggleSelect, onPreview, onDelete }: Props) {
  const lastSelectedIndexRef = useRef<number | null>(null);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
        event.preventDefault();
        assets.forEach((asset) => {
          if (!selectedIds.has(asset.asset_id)) {
            onToggleSelect(asset.asset_id);
          }
        });
      }
    },
    [assets, onToggleSelect, selectedIds]
  );

  if (assets.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-[#d0d7de] bg-[#f6f8fa] py-12 text-center text-sm text-[#57606a]">
        暂无素材，请先上传视频并索引
      </div>
    );
  }

  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      {assets.map((asset, index) => {
        const fileName = asset.file_path.split("/").pop() || asset.asset_id;

        return (
          <div
            key={asset.asset_id}
            onClick={(e) => {
              if (e.shiftKey && lastSelectedIndexRef.current !== null) {
                const start = Math.min(lastSelectedIndexRef.current, index);
                const end = Math.max(lastSelectedIndexRef.current, index);
                for (let i = start; i <= end; i += 1) {
                  const rangeAssetId = assets[i]?.asset_id;
                  if (rangeAssetId && !selectedIds.has(rangeAssetId)) {
                    onToggleSelect(rangeAssetId);
                  }
                }
              } else {
                onToggleSelect(asset.asset_id);
              }
              lastSelectedIndexRef.current = index;
            }}
            onDoubleClick={() => onPreview(asset)}
          >
            <AssetCard
              asset={{
                asset_id: asset.asset_id,
                name: fileName,
                size_bytes: 0,
                duration_seconds: asset.duration_seconds,
                in_use: asset.status === "available",
                category: asset.category,
                confidence: asset.confidence,
              }}
              selected={selectedIds.has(asset.asset_id)}
              onDelete={onDelete ? () => onDelete(asset.asset_id) : undefined}
            />
          </div>
        );
      })}
    </div>
  );
}
