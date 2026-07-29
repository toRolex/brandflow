import { DEFAULT_PAGE_SIZE, request } from "./core";

export interface LogDateInfo {
	date: string;
	size_bytes: number;
	error_count: number;
}

export interface LogDatePage {
	items: LogDateInfo[];
	total: number;
	page: number;
	page_size: number;
}

export interface LogEntry {
	source: "frontend" | "backend";
	level: "error" | "warn";
	message: string;
	timestamp?: string;
	status_code?: number;
	method?: string;
	path?: string;
	stack_trace?: string;
	request_body?: unknown;
	request_params?: Record<string, string>;
	extra?: Record<string, unknown>;
}

export const reportError = (entry: LogEntry) =>
	request<{ ok: boolean }>("/api/logs/error", {
		method: "POST",
		body: JSON.stringify(entry),
	});

export const listLogDates = (page = 1, pageSize = DEFAULT_PAGE_SIZE) =>
	request<LogDatePage>(`/api/logs/dates?page=${page}&page_size=${pageSize}`);

export const deleteLogDate = (date: string) =>
	request<{ date: string; deleted: boolean }>(`/api/logs/${date}`, {
		method: "DELETE",
	});

export const batchDeleteLogDates = (dates: string[]) =>
	request<{ deleted: string[]; not_found: string[]; protected: string[] }>(
		"/api/logs/batch",
		{
			method: "DELETE",
			body: JSON.stringify({ dates }),
		},
	);

export const cleanupLogs = (beforeDays: number) =>
	request<{ deleted: string[]; deleted_count: number }>(
		`/api/logs/cleanup?before_days=${beforeDays}`,
		{ method: "DELETE" },
	);

export const downloadLogUrl = (date: string) =>
	`/api/logs/download?date=${encodeURIComponent(date)}`;
