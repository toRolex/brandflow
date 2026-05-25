import type { ScheduleEntry } from "../types";

interface Props {
  entries: ScheduleEntry[];
  onExport: () => void;
}

const PLATFORM_LABELS: Record<string, string> = {
  douyin: "抖音",
  xiaohongshu: "小红书",
  shipinhao: "视频号",
  kuaishou: "快手",
};

export default function ScheduleTable({ entries, onExport }: Props) {
  return (
    <div>
      <div className="flex justify-end mb-3">
        <button
          className="bg-green-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-green-700 transition-colors"
          onClick={onExport}
        >
          导出 Excel
        </button>
      </div>
      {entries.length === 0 ? (
        <p className="text-gray-400 text-sm py-4">暂无排期数据</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left text-gray-500">
              <th className="py-2 px-3 font-medium">Job</th>
              <th className="py-2 px-3 font-medium">平台</th>
              <th className="py-2 px-3 font-medium">标题</th>
              <th className="py-2 px-3 font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id} className="border-b">
                <td className="py-2 px-3 font-mono text-xs">{e.job_id}</td>
                <td className="py-2 px-3">{PLATFORM_LABELS[e.platform] || e.platform}</td>
                <td className="py-2 px-3 max-w-xs truncate">{e.title || "-"}</td>
                <td className="py-2 px-3">
                  <span
                    className={`px-2 py-0.5 rounded text-xs ${
                      e.status === "published"
                        ? "bg-[#e6f4ea] text-[#1a7f37]"
                        : "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {e.status === "published" ? "已发布" : "待发布"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
