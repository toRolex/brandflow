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
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
        {Array.from({ length: 10 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-[var(--border-default)] p-4 animate-pulse"
          >
            <div className="h-4 bg-[var(--border-default)] rounded w-16 mb-2" />
            <div className="h-6 bg-[var(--border-default)] rounded w-24 mb-2" />
            <div className="h-3 bg-[var(--border-default)] rounded w-20" />
          </div>
        ))}
      </div>
    );
  }

  if (topics.length === 0) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
      {topics.map((t, i) => (
        <div
          key={t.keyword}
          className="rounded-xl border border-[var(--border-default)] p-4 bg-[var(--bg-card)]"
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-[var(--bg-tag-blue)] text-[var(--text-tag-blue)] text-xs font-bold">
              {i + 1}
            </span>
            <span className="text-sm font-medium text-[var(--text-primary)] truncate">
              {t.keyword}
            </span>
          </div>
          <div className="text-lg font-bold text-[var(--text-tag-blue)]">
            {formatNum(t.total_plays)}
          </div>
          <div className="text-xs text-[var(--text-secondary)]">
            {t.video_count} 条视频 · 完播 {t.avg_completion.toFixed(0)}%
          </div>
        </div>
      ))}
    </div>
  );
}
