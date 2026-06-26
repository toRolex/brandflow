import type { TopicStat } from "../types";

function formatNum(v: number): string {
  if (v >= 10000) return (v / 10000).toFixed(1) + "万";
  return v.toLocaleString();
}

export default function TopicGrid({
  topics,
  loading,
}: {
  topics: TopicStat[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-5 gap-3">
        {Array.from({ length: 10 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-gray-200 p-4 animate-pulse"
          >
            <div className="h-4 bg-gray-200 rounded w-16 mb-2" />
            <div className="h-6 bg-gray-200 rounded w-24 mb-2" />
            <div className="h-3 bg-gray-200 rounded w-20" />
          </div>
        ))}
      </div>
    );
  }

  if (topics.length === 0) return null;

  return (
    <div className="grid grid-cols-5 gap-3">
      {topics.map((t, i) => (
        <div
          key={t.keyword}
          className="rounded-xl border border-gray-200 p-4 bg-white"
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-50 text-blue-600 text-xs font-bold">
              {i + 1}
            </span>
            <span className="text-sm font-medium text-gray-800 truncate">
              {t.keyword}
            </span>
          </div>
          <div className="text-lg font-bold text-blue-600">
            {formatNum(t.total_plays)}
          </div>
          <div className="text-xs text-gray-500">
            {t.video_count} 条视频 · 完播 {(t.avg_completion * 100).toFixed(0)}%
          </div>
        </div>
      ))}
    </div>
  );
}
