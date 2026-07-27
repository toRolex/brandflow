export type ExportTaskStatus =
	| "not_started"
	| "queued"
	| "running"
	| "ready"
	| "failed"
	| "stale";

export interface ExportTaskState {
	task_id: string | null;
	status: ExportTaskStatus;
	progress: number;
	error: string | null;
}

export interface CreateExportResponse {
	task_id: string;
	status: Exclude<ExportTaskStatus, "not_started">;
}
