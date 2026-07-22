import type { AssetFile, AssetRecord, AssetStats } from "../types/asset";
import type { IndexResult } from "../types/assetIndexing";
import { request, uploadFile } from "./core";

export const uploadAsset = (projectId: string, file: File) =>
	uploadFile<AssetFile>(`/api/projects/${projectId}/upload`, file);

export const listAssets = (projectId: string) =>
	request<AssetFile[]>(`/api/projects/${projectId}/assets`);

export const listIndexedAssets = async (
	projectId: string,
	params?: { category?: string; q?: string; product?: string },
) => {
	const qs = new URLSearchParams();
	if (params?.category) qs.set("category", params.category);
	if (params?.q) qs.set("q", params.q);
	if (params?.product) qs.set("product", params.product);
	const res = await request<{
		assets: AssetRecord[];
		stats: {
			total_clips: number;
			available_clips: number;
			disabled_clips: number;
			source_videos: number;
		};
	}>(`/api/projects/${projectId}/assets/indexed?${qs.toString()}`);
	return {
		assets: res.assets,
		stats: {
			total: res.stats.total_clips,
			available: res.stats.available_clips,
			disabled: res.stats.disabled_clips,
			source_videos: res.stats.source_videos,
		} as AssetStats,
	};
};

export const indexAssets = (projectId: string) =>
	request<IndexResult>(`/api/projects/${projectId}/assets/index`, {
		method: "POST",
	});

export const updateAssetStatus = (
	projectId: string,
	assetIds: string[],
	status: string,
) =>
	request<{ updated: number }>(`/api/projects/${projectId}/assets/batch`, {
		method: "PATCH",
		body: JSON.stringify({ asset_ids: assetIds, status }),
	});

export const deleteAsset = (projectId: string, name: string) =>
	request<{ status: string }>(
		`/api/projects/${projectId}/assets/${encodeURIComponent(name)}`,
		{
			method: "DELETE",
		},
	);
