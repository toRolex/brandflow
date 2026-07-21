export type ExportTaskStatus =
	| "queued"
	| "running"
	| "ready"
	| "failed"
	| "stale";

export interface ExportTaskState {
	task_id: string;
	status: ExportTaskStatus;
	progress: number;
	error: string | null;
}

export interface CreateExportResponse {
	task_id: string;
	status: ExportTaskStatus;
}
