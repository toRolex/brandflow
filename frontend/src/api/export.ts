import type { CreateExportResponse, ExportTaskState } from "../types/export";

export const createExport = async (jobId: string) => {
	const res = await fetch(`/api/jobs/${jobId}/export`, {
		method: "POST",
	});
	if (!res.ok) {
		const text = await res.text();
		throw new Error(`${res.status}: ${text}`);
	}
	return res.json() as Promise<CreateExportResponse>;
};

export const getExportStatus = async (jobId: string) => {
	const res = await fetch(`/api/jobs/${jobId}/export/status`);
	if (res.status === 404) return null;
	if (!res.ok) {
		const text = await res.text();
		throw new Error(`${res.status}: ${text}`);
	}
	return res.json() as Promise<ExportTaskState>;
};

export const downloadExport = async (jobId: string) => {
	const res = await fetch(`/api/jobs/${jobId}/export/download`);
	if (!res.ok) {
		const text = await res.text();
		throw new Error(`${res.status}: ${text}`);
	}
	return res.blob();
};
