import type {
	AssetFile,
	CategoryItem,
	SuggestCategory,
} from "../types/asset";
import type { IndexResult, IndexTaskState } from "../types/assetIndexing";
import { fetchIndexedAssets } from "./indexedAssets";
import { request, uploadFile } from "./core";

export const uploadAssetShared = (file: File) =>
	uploadFile<AssetFile>("/api/assets/upload", file);

export const listIndexedAssetsShared = (params?: Parameters<
	typeof fetchIndexedAssets
>[1]) => fetchIndexedAssets("/api/assets/indexed", params);

export const indexAssetsShared = () =>
	request<IndexResult>("/api/assets/index", {
		method: "POST",
	});

export const indexAssetsSharedAsync = (sourcePaths?: string[]) =>
	request<{ task_id: string; total_videos: number }>(
		"/api/assets/index?async_mode=true",
		{
			method: "POST",
			body: sourcePaths
				? JSON.stringify({ source_paths: sourcePaths })
				: undefined,
		},
	);

export const getIndexStatus = (taskId: string) =>
	request<IndexTaskState>(`/api/assets/index/${taskId}/status`);

export const getIndexLogsUrl = (taskId: string) =>
	`/api/assets/index/${taskId}/logs`;

export const updateAssetStatusShared = (assetIds: string[], status: string) =>
	request<{ updated: number }>("/api/assets/batch", {
		method: "PATCH",
		body: JSON.stringify({ asset_ids: assetIds, status }),
	});

export const updateAssetFields = (
	assetId: string,
	fields: { product?: string; category?: string },
) =>
	request<{ updated: number }>(`/api/assets/${assetId}/fields`, {
		method: "PATCH",
		body: JSON.stringify(fields),
	});

export const batchUpdateAssetFields = (
	assetIds: string[],
	fields: { product?: string; category?: string },
) =>
	request<{ updated: number }>("/api/assets/batch-fields", {
		method: "PATCH",
		body: JSON.stringify({ asset_ids: assetIds, ...fields }),
	});

export const deleteAssetShared = (assetId: string) =>
	request<{ status: string }>(`/api/assets/${assetId}`, {
		method: "DELETE",
	});

export const batchDeleteAssets = (assetIds: string[]) =>
	request<{ deleted: number; files_deleted: number }>("/api/assets/batch", {
		method: "DELETE",
		body: JSON.stringify({ asset_ids: assetIds }),
	});

export const batchReclassifyAssets = (assetIds: string[], category: string) =>
	request<{ updated: number }>("/api/assets/categories", {
		method: "PATCH",
		body: JSON.stringify({ asset_ids: assetIds, category }),
	});

export const migrateAssets = () =>
	request<{
		migrated_projects: number;
		migrated_clips: number;
		migrated_sources: number;
	}>("/api/assets/migrate", { method: "POST" });

export const listCategories = () =>
	request<CategoryItem[]>("/api/assets/categories");

export const suggestCategories = () =>
	request<{
		suggestions: SuggestCategory[];
		errors: string[];
	}>("/api/assets/categories/suggest", {
		method: "POST",
		body: JSON.stringify({}),
	});
