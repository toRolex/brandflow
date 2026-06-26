import { useState, useCallback, useEffect, useRef } from "react";
import { api } from "../api/client";
import type {
  MetricsOverview,
  TopicStat,
  VideoMetric,
  VideoMetricPage,
} from "../types";
import MetricsCards from "../components/MetricsCards";
import TrendChart from "../components/TrendChart";
import TopicGrid from "../components/TopicGrid";
import VideoTable from "../components/VideoTable";
import AssetDetailModal from "../components/AssetDetailModal";

const DAYS_OPTIONS = [
  { value: 1, label: "1天" },
  { value: 7, label: "7天" },
  { value: 30, label: "30天" },
];

const PLATFORM_OPTIONS = [
  { value: "", label: "全部" },
  { value: "weixin", label: "视频号" },
  { value: "xiaohongshu", label: "小红书" },
];

export default function AnalyticsPage() {
  const [days, setDays] = useState(7);
  const [platform, setPlatform] = useState("");
  const [sortBy, setSortBy] = useState("plays_desc");
  const [search, setSearch] = useState("");
  const [overview, setOverview] = useState<MetricsOverview | null>(null);
  const [topics, setTopics] = useState<TopicStat[]>([]);
  const [videoPage, setVideoPage] = useState<VideoMetricPage | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [topicsLoading, setTopicsLoading] = useState(true);
  const [videosLoading, setVideosLoading] = useState(true);
  const [assetVideo, setAssetVideo] = useState<VideoMetric | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const fetchData = useCallback(() => {
    const p = platform || undefined;

    setOverviewLoading(true);
    api
      .getMetricsOverview(days, p)
      .then(setOverview)
      .catch(() => setOverview(null))
      .finally(() => setOverviewLoading(false));

    setTopicsLoading(true);
    api
      .getMetricsTopics(30, p, 10)
      .then(setTopics)
      .catch(() => setTopics([]))
      .finally(() => setTopicsLoading(false));

    setVideosLoading(true);
    api
      .getMetricsVideos({
        sort_by: sortBy,
        platform: p,
        search: search || undefined,
        page: 1,
        page_size: 50,
      })
      .then(setVideoPage)
      .catch(() => setVideoPage(null))
      .finally(() => setVideosLoading(false));
  }, [days, platform, sortBy, search]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    try {
      const res = await api.uploadMetrics(file);
      const msg = res.error
        ? `导入部分完成: inserted=${res.inserted}, updated=${res.updated}, error=${res.error}`
        : `导入完成: inserted=${res.inserted}, updated=${res.updated}`;
      alert(msg);
      fetchData();
    } catch (e) {
      alert("导入失败: " + (e as Error).message);
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleScan = async () => {
    try {
      const res = await api.scanMetrics();
      alert(
        `扫描完成: 处理 ${res.files_processed} 个文件, inserted=${res.inserted}, updated=${res.updated}`
      );
      fetchData();
    } catch (e) {
      alert("扫描失败: " + (e as Error).message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-semibold text-gray-800 mr-auto">
          内容运营数据追踪
        </h1>

        {/* Days filter */}
        <div className="flex items-center gap-1">
          {DAYS_OPTIONS.map((d) => (
            <button
              key={d.value}
              onClick={() => setDays(d.value)}
              className={`px-3 py-1 text-sm rounded-lg border transition-colors ${
                days === d.value
                  ? "bg-blue-50 border-blue-300 text-blue-700"
                  : "border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>

        {/* Platform filter */}
        <div className="flex items-center gap-1">
          {PLATFORM_OPTIONS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPlatform(p.value)}
              className={`px-3 py-1 text-sm rounded-lg border transition-colors ${
                platform === p.value
                  ? "bg-blue-50 border-blue-300 text-blue-700"
                  : "border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Scan & Upload */}
        <button
          onClick={handleScan}
          className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50"
        >
          扫描 data/
        </button>
        <label className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 cursor-pointer">
          📥 导入数据
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx"
            onChange={handleUpload}
            className="hidden"
          />
        </label>
      </div>

      {/* Summary cards */}
      <MetricsCards data={overview} loading={overviewLoading} />

      {/* Trend chart */}
      <TrendChart data={overview} />

      {/* Topic grid */}
      <div>
        <div className="text-sm text-gray-500 mb-2">热门话题 Top10</div>
        <TopicGrid topics={topics} loading={topicsLoading} />
      </div>

      {/* Video table */}
      <VideoTable
        videos={videoPage?.items ?? []}
        total={videoPage?.total ?? 0}
        loading={videosLoading}
        sortBy={sortBy}
        onSortChange={setSortBy}
        onSearchChange={setSearch}
        onPlatformChange={setPlatform}
        onAssetClick={setAssetVideo}
      />

      {/* Asset detail modal */}
      <AssetDetailModal
        video={assetVideo}
        onClose={() => setAssetVideo(null)}
      />
    </div>
  );
}
