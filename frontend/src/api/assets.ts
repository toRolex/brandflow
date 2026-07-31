import type { AssetFile } from "../types/asset";
import type { IndexResult } from "../types/assetIndexing";
import { request, uploadFile } from "./core";

export const uploadAsset = (projectId: string, file: File) =>
	uploadFile<AssetFile>(`/api/projects/${projectId}/upload`, file);

export const listAssets = (projectId: string) =>
	request<AssetFile[]>(`/api/projects/${projectId}/assets`);

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
