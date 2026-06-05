import { useState } from "react";

interface ClipData {
  sentence: string;
  category: string;
  requested_category?: string;
  file_path: string;
  asset_id: string;
  method: string;
}

interface Props {
  clip: ClipData;
  index: number;
  onReject: (index: number) => void;
  rejected?: boolean;
}

export default function ClipReviewCard({ clip, index, onReject, rejected = false }: Props) {
  const [imgError, setImgError] = useState(false);
  const thumbnailUrl = clip.asset_id ? `/api/assets/${clip.asset_id}/thumbnail` : null;
  const fileName = clip.file_path.split("/").pop() || clip.asset_id;

  const isFallback = clip.method === "fallback";
  const hasDowngradeInfo = isFallback && clip.requested_category && clip.requested_category !== clip.category;

  return (
    <div className={`border rounded-lg overflow-hidden transition-colors max-w-full ${rejected ? "border-[#d1242f] bg-[#ffebe9]" : "border-[#d0d7de] bg-white"}`}>
      <div className="p-3 bg-[#f6f8fa] border-b border-[#d0d7de]">
        <div className="flex items-start gap-2">
          <span className="text-[#57606a] text-xs font-mono shrink-0">#{index + 1}</span>
          <p className="text-sm text-[#1f2328] leading-relaxed break-words">{clip.sentence}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <span className="inline-flex px-1.5 py-0.5 rounded text-xs bg-[#eaeef2] text-[#59636e]">
            {clip.category}
          </span>
          {hasDowngradeInfo ? (
            <span className="text-xs text-[#9a6700]">
              想匹配：{clip.requested_category} → 降级为：{clip.category}
            </span>
          ) : (
            <span className={`text-xs ${clip.method === "llm_match" ? "text-[#1a7f37]" : "text-[#9a6700]"}`}>
              {clip.method === "llm_match" ? "LLM 匹配" : "降级匹配"}
            </span>
          )}
        </div>
      </div>
      <div className="p-3">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-20 h-14 bg-[#eff2f5] rounded overflow-hidden flex-shrink-0">
            {thumbnailUrl && !imgError ? (
              <img
                src={thumbnailUrl}
                alt={fileName}
                className="w-full h-full object-cover"
                onError={() => setImgError(true)}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-lg">🎬</div>
            )}
          </div>
          <div className="flex-1 min-w-0 overflow-hidden">
            <div className="text-xs font-medium truncate" title={fileName}>{fileName}</div>
            <div className="text-xs text-gray-500 mt-0.5 truncate">{clip.asset_id}</div>
          </div>
        </div>
        <button
          type="button"
          className="w-full px-3 py-1.5 rounded text-xs font-medium transition-colors bg-[#d1242f] text-white hover:bg-[#b6232d]"
          onClick={() => onReject(index)}
        >
          打回检索
        </button>
      </div>
    </div>
  );
}
