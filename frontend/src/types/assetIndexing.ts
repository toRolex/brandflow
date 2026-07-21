export type IndexStatus = "idle" | "processing" | "done";

export interface IndexResult {
	indexed: number;
	skipped: number;
	total_clips: number;
}

export type IndexTaskStatus = "pending" | "running" | "completed" | "failed";

export interface IndexTaskState {
	task_id: string;
	status: IndexTaskStatus;
	progress: number;
	current_step: string;
	current_video: number;
	total_videos: number;
	error: string | null;
}
