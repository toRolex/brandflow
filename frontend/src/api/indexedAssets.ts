import type { AssetRecord, AssetStats } from "../types/asset";
import { request } from "./core";

export interface IndexedAssetParams {
	category?: string;
	q?: string;
	product?: string;
	status?: string;
	durationMin?: number;
	durationMax?: number;
	confidenceMin?: number;
	confidenceMax?: number;
	usageMin?: number;
	usageMax?: number;
	page?: number;
	pageSize?: number;
}

interface RawIndexedResponse {
	assets: AssetRecord[];
	stats: {
		total_clips: number;
		available_clips: number;
		disabled_clips: number;
		source_videos: number;
		category_counts?: Record<string, number>;
		duration_min?: number;
		duration_max?: number;
		usage_min?: number;
		usage_max?: number;
	};
	page?: number;
	page_size?: number;
	total?: number;
}

export function buildIndexedAssetQuery(params?: IndexedAssetParams): string {
	const qs = new URLSearchParams();
	if (params?.category) qs.set("category", params.category);
	if (params?.q) qs.set("q", params.q);
	if (params?.product) qs.set("product", params.product);
	if (params?.status) qs.set("status", params.status);
	if (params?.durationMin !== undefined && params.durationMin > 0)
		qs.set("duration_min", String(params.durationMin));
	if (params?.durationMax !== undefined && params.durationMax > 0)
		qs.set("duration_max", String(params.durationMax));
	if (params?.confidenceMin !== undefined)
		qs.set("confidence_min", String(params.confidenceMin));
	if (params?.confidenceMax !== undefined && params.confidenceMax < 1)
		qs.set("confidence_max", String(params.confidenceMax));
	if (params?.usageMin !== undefined && params.usageMin > 0)
		qs.set("usage_min", String(params.usageMin));
	if (params?.usageMax !== undefined && params.usageMax > 0)
		qs.set("usage_max", String(params.usageMax));
	if (params?.page !== undefined) qs.set("page", String(params.page));
	if (params?.pageSize !== undefined) qs.set("page_size", String(params.pageSize));
	return qs.toString();
}

function normalizeStats(raw: RawIndexedResponse["stats"]): AssetStats {
	return {
		total: raw.total_clips,
		available: raw.available_clips,
		disabled: raw.disabled_clips,
		source_videos: raw.source_videos,
		category_counts: raw.category_counts ?? {},
		duration_min: raw.duration_min ?? 0,
		duration_max: raw.duration_max ?? 0,
		usage_min: raw.usage_min ?? 0,
		usage_max: raw.usage_max ?? 0,
	};
}

export async function fetchIndexedAssets(
	path: string,
	params?: IndexedAssetParams,
): Promise<{
	assets: AssetRecord[];
	stats: AssetStats;
	page: number;
	pageSize: number;
	total: number;
}> {
	const qs = buildIndexedAssetQuery(params);
	const res = await request<RawIndexedResponse>(`${path}?${qs}`);
	return {
		assets: res.assets,
		stats: normalizeStats(res.stats),
		page: res.page ?? 1,
		pageSize: res.page_size ?? res.assets.length,
		total: res.total ?? res.assets.length,
	};
}
