import { useState, useEffect } from "react";
import { api } from "../api/client";

interface TTSMetrics {
  time_range: string;
  total_requests: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  avg_latency_ms: number;
  avg_audio_duration_ms: number;
  total_audio_duration_ms: number;
  error_distribution: Record<string, number>;
  voice_distribution: Record<string, number>;
}

interface TTSLog {
  id: string;
  task_id: string;
  timestamp: string;
  voice_id: string;
  success: boolean;
  latency_ms: number;
  audio_duration_ms: number | null;
  error_type: string | null;
  error_message: string | null;
}

const TIME_RANGES = [
  { label: "1小时", value: "1h" },
  { label: "24小时", value: "24h" },
  { label: "7天", value: "7d" },
  { label: "30天", value: "30d" },
];

export default function TTSMonitorPage() {
  const [metrics, setMetrics] = useState<TTSMetrics | null>(null);
  const [logs, setLogs] = useState<TTSLog[]>([]);
  const [timeRange, setTimeRange] = useState("24h");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, [timeRange]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [metricsData, logsData] = await Promise.all([
        api.getTTSMetrics(undefined, timeRange),
        api.getTTSLogs({ limit: 10 }),
      ]);
      setMetrics(metricsData as unknown as TTSMetrics);
      setLogs(logsData as unknown as TTSLog[]);
    } catch {
      console.error("加载监控数据失败");
    }
    setLoading(false);
  };

  if (loading || !metrics) {
    return <div className="text-center py-12 text-gray-400">加载监控数据中...</div>;
  }

  const errorEntries = Object.entries(metrics.error_distribution).sort((a, b) => b[1] - a[1]);
  const totalErrors = errorEntries.reduce((sum, [, count]) => sum + count, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">TTS 监控</h1>
        <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-1">
          {TIME_RANGES.map(range => (
            <button
              key={range.value}
              className={`px-3 py-1 text-sm rounded-md ${
                timeRange === range.value
                  ? "bg-white text-gray-800 shadow-sm"
                  : "text-gray-600 hover:text-gray-800"
              }`}
              onClick={() => setTimeRange(range.value)}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-5 gap-4 mb-6">
        <div className="bg-gradient-to-br from-purple-500 to-indigo-600 rounded-xl p-4 text-white">
          <p className="text-sm opacity-90">总请求</p>
          <p className="text-3xl font-bold mt-1">{metrics.total_requests.toLocaleString()}</p>
        </div>
        <div className="bg-gradient-to-br from-green-400 to-teal-500 rounded-xl p-4 text-white">
          <p className="text-sm opacity-90">成功率</p>
          <p className="text-3xl font-bold mt-1">{(metrics.success_rate * 100).toFixed(1)}%</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-sm text-gray-500">平均延迟</p>
          <p className="text-3xl font-bold text-gray-800 mt-1">{(metrics.avg_latency_ms / 1000).toFixed(1)}s</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <p className="text-sm text-gray-500">总音频时长</p>
          <p className="text-3xl font-bold text-gray-800 mt-1">{Math.round(metrics.total_audio_duration_ms / 60000)}min</p>
        </div>
        <div className="bg-gradient-to-br from-orange-400 to-pink-500 rounded-xl p-4 text-white">
          <p className="text-sm opacity-90">失败次数</p>
          <p className="text-3xl font-bold mt-1">{metrics.failure_count}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold mb-4">错误分布</h2>
          <div className="space-y-3">
            {errorEntries.map(([type, count]) => (
              <div key={type}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-600">{type}</span>
                  <span className="font-medium">{count}次 ({((count / totalErrors) * 100).toFixed(0)}%)</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full"
                    style={{ width: `${(count / totalErrors) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            {errorEntries.length === 0 && (
              <p className="text-gray-400 text-center py-4">暂无错误数据</p>
            )}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold mb-4">音色使用分布</h2>
          <div className="grid grid-cols-2 gap-4">
            {Object.entries(metrics.voice_distribution)
              .sort((a, b) => b[1] - a[1])
              .slice(0, 4)
              .map(([voice, count]) => (
                <div key={voice} className="text-center p-4 bg-gray-50 rounded-xl">
                  <div className="w-12 h-12 bg-blue-500 rounded-full flex items-center justify-center text-white text-xl mx-auto mb-2">
                    {voice[0]}
                  </div>
                  <p className="font-medium text-gray-800">{voice}</p>
                  <p className="text-xl font-bold text-blue-500">{count}</p>
                </div>
              ))}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold mb-4">最近请求</h2>
        <div className="space-y-2">
          {logs.map(log => (
            <div
              key={log.id}
              className={`flex items-center gap-3 p-3 rounded-lg ${
                log.success ? "bg-green-50" : "bg-red-50"
              }`}
            >
              <span className={log.success ? "text-green-500" : "text-red-500"}>
                {log.success ? "✓" : "✗"}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{log.task_id}</p>
                <p className="text-xs text-gray-500">
                  {log.voice_id} · {(log.latency_ms / 1000).toFixed(1)}s
                  {log.audio_duration_ms && ` · ${(log.audio_duration_ms / 1000).toFixed(1)}s音频`}
                  {log.error_type && <span className="text-red-500"> · {log.error_type}</span>}
                </p>
              </div>
              <span className="text-xs text-gray-400">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
            </div>
          ))}
          {logs.length === 0 && (
            <p className="text-gray-400 text-center py-4">暂无请求记录</p>
          )}
        </div>
      </div>
    </div>
  );
}
