import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { VideoMetric, AssetRecord } from "../types";

interface Props {
  video: VideoMetric | null;
  onClose: () => void;
}

export default function AssetDetailModal({ video, onClose }: Props) {
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!video) return;
    setLoading(true);
    api
      .listIndexedAssetsShared()
      .then((res) => {
        const filtered = res.assets.filter((a) =>
          video.used_asset_ids.includes(a.asset_id)
        );
        setAssets(filtered);
      })
      .catch(() => setAssets([]))
      .finally(() => setLoading(false));
  }, [video]);

  if (!video) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-[560px] max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <div>
            <h3 className="text-base font-semibold text-gray-800 truncate max-w-[400px]">
              {video.title}
            </h3>
            <div className="text-xs text-gray-500 mt-0.5">
              {video.platform === "weixin" ? "视频号" : "小红书"} ·{" "}
              {video.publish_date} · 播放 {video.plays.toLocaleString()}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none px-2"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="p-5">
          {loading ? (
            <div className="text-center text-gray-400 py-6">加载中...</div>
          ) : assets.length === 0 ? (
            <div className="text-center text-gray-400 py-6">
              未找到关联素材
            </div>
          ) : (
            <div className="space-y-3">
              {assets.map((a) => (
                <div
                  key={a.asset_id}
                  className="rounded-lg border border-gray-200 p-3"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-gray-800">
                      {a.category}
                    </span>
                    <span className="text-xs text-gray-500">
                      {a.product}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500 mb-2">
                    <span>
                      置信度 {(a.confidence * 100).toFixed(0)}%
                    </span>
                    <span>时长 {a.duration_seconds.toFixed(1)}s</span>
                  </div>
                  {a.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {a.tags.map((t) => (
                        <span
                          key={t}
                          className="px-1.5 py-0.5 text-[11px] rounded bg-gray-100 text-gray-600"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
