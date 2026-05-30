import type { AssetFile } from "../types";

type AssetCardData = AssetFile & {
  category?: string;
  confidence?: number;
};

interface Props {
  asset: AssetCardData;
  onDelete?: (name: string) => void;
  selected?: boolean;
  onSelect?: (name: string, event: React.MouseEvent<HTMLButtonElement>) => void;
}

export default function AssetCard({ asset, onDelete, selected = false, onSelect }: Props) {
  const seconds = asset.duration_seconds || 0;
  const min = Math.floor(seconds / 60);
  const sec = String(Math.floor(seconds % 60)).padStart(2, "0");
  const confidence = typeof asset.confidence === "number"
    ? `${Math.round(asset.confidence * 100)}%`
    : null;

  const containerClass = selected
    ? "border-[#0969da] bg-[#ddf4ff]"
    : asset.in_use
      ? "border-[#1a7f37] bg-[#e6f4ea]"
      : "border-[#d0d7de] bg-white";

  const isSelectable = Boolean(onSelect);

  return (
    <div
      className={`w-44 text-left border rounded-lg overflow-hidden flex-shrink-0 transition-colors ${containerClass}`}
      role="group"
    >
      <div className="h-[90px] bg-[#eff2f5] flex items-center justify-center text-[28px]">
        {"🎬"}
      </div>
      <div className="p-2 text-xs">
        <div className="font-medium truncate" title={asset.name}>{asset.name}</div>
        {asset.category && (
          <div className="inline-flex mt-1 px-1.5 py-0.5 rounded bg-[#eaeef2] text-[#59636e]">
            {asset.category}
          </div>
        )}
        {seconds > 0 && <div className="text-gray-500 mt-1">{min}:{sec}</div>}
        {confidence && <div className="text-[#0969da] mt-0.5">置信度 {confidence}</div>}
        {asset.in_use && <div className="text-green-600 mt-0.5">&#10003; 使用中</div>}
        {selected && <div className="text-[#0969da] mt-0.5">&#10003; 已选中</div>}
        <div className="mt-1 flex items-center gap-2">
          {isSelectable && (
            <button
              type="button"
              className="text-[#0969da] hover:underline"
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
              className="text-red-500 hover:underline"
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
