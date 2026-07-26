import { request } from "./core";

export interface LogDateInfo {
	date: string;
	size_bytes: number;
	error_count: number;
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

export const listLogDates = () => request<LogDateInfo[]>("/api/logs/dates");

export const downloadLogUrl = (date: string) =>
	`/api/logs/download?date=${encodeURIComponent(date)}`;
