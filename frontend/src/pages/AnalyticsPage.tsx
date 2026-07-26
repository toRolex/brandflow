import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { DEFAULT_PAGE_SIZE } from "../api/core";
import AssetDetailModal from "../components/AssetDetailModal";
import MetricsCards from "../components/MetricsCards";
import TopicGrid from "../components/TopicGrid";
import TrendChart from "../components/TrendChart";
import VideoTable from "../components/VideoTable";
import type {
	MetricsOverview,
	TopicStat,
	VideoMetric,
	VideoMetricPage,
} from "../types";

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
	const [page, setPage] = useState(1);
	const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
	const [refreshVersion, setRefreshVersion] = useState(0);
	const fileRef = useRef<HTMLInputElement>(null);
	const overviewRequestIdRef = useRef(0);
	const topicsRequestIdRef = useRef(0);
	const videosRequestIdRef = useRef(0);

	const fetchOverview = useCallback(() => {
		const p = platform || undefined;
		setOverviewLoading(true);
		const requestId = ++overviewRequestIdRef.current;
		api
			.getMetricsOverview(days, p)
			.then((result) => {
				if (requestId === overviewRequestIdRef.current) {
					setOverview(result);
				}
			})
			.catch(() => {
				if (requestId === overviewRequestIdRef.current) {
					setOverview(null);
				}
			})
			.finally(() => {
				if (requestId === overviewRequestIdRef.current) {
					setOverviewLoading(false);
				}
			});
	}, [days, platform]);

	const fetchTopics = useCallback(() => {
		const p = platform || undefined;
		setTopicsLoading(true);
		const requestId = ++topicsRequestIdRef.current;
		api
			.getMetricsTopics(30, p, 10)
			.then((result) => {
				if (requestId === topicsRequestIdRef.current) {
					setTopics(result);
				}
			})
			.catch(() => {
				if (requestId === topicsRequestIdRef.current) {
					setTopics([]);
				}
			})
			.finally(() => {
				if (requestId === topicsRequestIdRef.current) {
					setTopicsLoading(false);
				}
			});
	}, [platform]);

	const fetchVideos = useCallback(() => {
		const p = platform || undefined;
		setVideosLoading(true);
		const videosRequestId = ++videosRequestIdRef.current;
		api
			.getMetricsVideos({
				sort_by: sortBy,
				platform: p,
				search: search || undefined,
				page,
				page_size: pageSize,
			})
			.then((result) => {
				if (videosRequestId === videosRequestIdRef.current) {
					setVideoPage(result);
				}
			})
			.catch(() => {
				if (videosRequestId === videosRequestIdRef.current) {
					setVideoPage(null);
				}
			})
			.finally(() => {
				if (videosRequestId === videosRequestIdRef.current) {
					setVideosLoading(false);
				}
			});
	}, [platform, sortBy, search, page, pageSize]);

	useEffect(() => {
		fetchOverview();
	}, [fetchOverview, refreshVersion]);

	useEffect(() => {
		fetchTopics();
	}, [fetchTopics, refreshVersion]);

	useEffect(() => {
		fetchVideos();
	}, [fetchVideos, refreshVersion]);

	const withPageReset = <T,>(fn: (v: T) => void) => (v: T) => {
		fn(v);
		setPage(1);
	};

	const handleDaysChange = setDays;
	const handlePlatformChange = withPageReset(setPlatform);
	const handleSortChange = withPageReset(setSortBy);
	const handleSearchChange = withPageReset(setSearch);

	const handlePageChange = (p: number) => setPage(p);

	const handlePageSizeChange = (s: number) => {
		setPageSize(s);
		setPage(1);
	};

	const handleUpload = async () => {
		const file = fileRef.current?.files?.[0];
		if (!file) return;
		try {
			const res = await api.uploadMetrics(file);
			const msg = res.error
				? `导入部分完成: inserted=${res.inserted}, updated=${res.updated}, error=${res.error}`
				: `导入完成: inserted=${res.inserted}, updated=${res.updated}`;
			alert(msg);
			setRefreshVersion((version) => version + 1);
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
				`扫描完成: 处理 ${res.files_processed} 个文件, inserted=${res.inserted}, updated=${res.updated}`,
			);
			setRefreshVersion((version) => version + 1);
		} catch (e) {
			alert("扫描失败: " + (e as Error).message);
		}
	};

	return (
		<div className="space-y-6">
			{/* Top bar */}
			<div className="flex items-center gap-3 flex-wrap">
				<h1 className="text-lg font-semibold text-[var(--text-primary)] mr-auto">
					内容运营数据追踪
				</h1>

				{/* Days filter */}
				<div className="flex items-center gap-1">
					{DAYS_OPTIONS.map((d) => (
						<button
							key={d.value}
							onClick={() => handleDaysChange(d.value)}
							className={`px-3 py-1 text-sm rounded-lg border transition-colors ${
								days === d.value
									? "bg-[var(--bg-nav-active)] border-[var(--accent)] text-[var(--accent)]"
									: "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]"
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
							onClick={() => handlePlatformChange(p.value)}
							className={`px-3 py-1 text-sm rounded-lg border transition-colors ${
								platform === p.value
									? "bg-[var(--bg-nav-active)] border-[var(--accent)] text-[var(--accent)]"
									: "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]"
							}`}
						>
							{p.label}
						</button>
					))}
				</div>

				{/* Scan & Upload */}
				<button
					onClick={handleScan}
					className="px-3 py-1.5 text-sm rounded-lg border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]"
				>
					扫描 data/
				</button>
				<label className="px-3 py-1.5 text-sm rounded-lg border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)] cursor-pointer">
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
				<div className="text-sm text-[var(--text-tertiary)] mb-2">
					热门话题 Top10
				</div>
				<TopicGrid topics={topics} loading={topicsLoading} />
			</div>

			{/* Video table */}
			<VideoTable
				videos={videoPage?.items ?? []}
				total={videoPage?.total ?? 0}
				loading={videosLoading}
				sortBy={sortBy}
				onSortChange={handleSortChange}
				onSearchChange={handleSearchChange}
				onPlatformChange={handlePlatformChange}
				onAssetClick={setAssetVideo}
				page={page}
				pageSize={pageSize}
				onPageChange={handlePageChange}
				onPageSizeChange={handlePageSizeChange}
			/>

			{/* Asset detail modal */}
			<AssetDetailModal
				video={assetVideo}
				onClose={() => setAssetVideo(null)}
			/>
		</div>
	);
}
