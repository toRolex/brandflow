import type { MetricsOverview } from "../types";

const ITEMS = [
  { key: "total_plays" as const, label: "总播放量", color: "text-blue-600" },
  { key: "total_likes" as const, label: "总点赞", color: "text-pink-600" },
  { key: "total_followers" as const, label: "总涨粉", color: "text-green-600" },
  {
    key: "avg_completion" as const,
    label: "平均完播率",
    color: "text-purple-600",
    isRate: true,
  },
];

function formatNum(v: number): string {
  if (v >= 10000) return (v / 10000).toFixed(1) + "万";
  return v.toLocaleString();
}

export default function MetricsCards({
  data,
  loading,
}: {
  data: MetricsOverview | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-gray-200 p-5 animate-pulse"
          >
            <div className="h-4 bg-gray-200 rounded w-20 mb-3" />
            <div className="h-8 bg-gray-200 rounded w-28" />
          </div>
        ))}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      {ITEMS.map((it) => {
        const raw = data[it.key];
        const display = it.isRate
          ? raw.toFixed(1) + "%"
          : formatNum(raw as number);
        return (
          <div
            key={it.key}
            className="rounded-xl border border-gray-200 p-5 bg-white"
          >
            <div className="text-sm text-gray-500 mb-1">{it.label}</div>
            <div className={`text-2xl font-bold ${it.color}`}>{display}</div>
          </div>
        );
      })}
    </div>
  );
}
