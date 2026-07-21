import { request, uploadFile } from "./core";

export const listDocuments = () =>
	request<{
		documents: {
			id: string;
			filename: string;
			source_type: string;
			item_count: number;
		}[];
	}>("/api/knowledge/documents");

export const uploadKnowledge = (file: File) =>
	uploadFile<{ status: string; filename: string; item_count: number }>(
		"/api/knowledge/upload",
		file,
	);

export const refreshKnowledge = () =>
	request<{ message: string }>("/api/knowledge/refresh", { method: "POST" });
