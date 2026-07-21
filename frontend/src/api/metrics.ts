import { request, uploadFile } from "./core";
import type {
	ImportResult,
	MetricsOverview,
	ScanResult,
	TopicStat,
	VideoMetricPage,
} from "../types/metrics";

export const uploadMetrics = (file: File) =>
	uploadFile<ImportResult>("/api/metrics/upload", file);

export const scanMetrics = () =>
	request<ScanResult>("/api/metrics/scan", {
		method: "POST",
	});

export const getMetricsOverview = (days: number = 7, platform?: string) => {
	const qs = new URLSearchParams();
	qs.set("days", String(days));
	if (platform) qs.set("platform", platform);
	return request<MetricsOverview>(
		`/api/metrics/overview?${qs.toString()}`,
	);
};

export const getMetricsVideos = (params?: {
	sort_by?: string;
	platform?: string;
	search?: string;
	page?: number;
	page_size?: number;
}) => {
	const qs = new URLSearchParams();
	if (params?.sort_by) qs.set("sort_by", params.sort_by);
	if (params?.platform) qs.set("platform", params.platform);
	if (params?.search) qs.set("search", params.search);
	if (params?.page) qs.set("page", String(params.page));
	if (params?.page_size) qs.set("page_size", String(params.page_size));
	return request<VideoMetricPage>(
		`/api/metrics/videos?${qs.toString()}`,
	);
};

export const getMetricsTopics = (
	days: number = 30,
	platform?: string,
	limit: number = 10,
) => {
	const qs = new URLSearchParams();
	qs.set("days", String(days));
	if (platform) qs.set("platform", platform);
	qs.set("limit", String(limit));
	return request<TopicStat[]>(`/api/metrics/topics?${qs.toString()}`);
};
