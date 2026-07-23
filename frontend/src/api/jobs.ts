import type { ProductionMode, ReviewStrategy } from "../types/core";
import type {
	BatchCreateRequest,
	BatchCreateResponse,
	JobDetail,
} from "../types/job";
import { request, uploadFile } from "./core";

export const createJob = (
	projectId: string,
	body: {
		platforms: string[];
		name?: string;
		mode?: ProductionMode;
		manual_script?: string;
		skip_subtitle?: boolean;
		review_strategy?: ReviewStrategy;
		audio_source?: string;
		music_track_path?: string;
		music_volume?: number;
		language?: string;
		cover_title?: { text: string; highlight_words?: string[] } | null;
	},
) =>
	request<JobDetail>("/api/projects/" + projectId + "/jobs", {
		method: "POST",
		body: JSON.stringify(body),
	});

export const batchCreateJobs = (projectId: string, body: BatchCreateRequest) =>
	request<BatchCreateResponse>(`/api/projects/${projectId}/jobs/batch`, {
		method: "POST",
		body: JSON.stringify(body),
	});

export const getJob = (jobId: string) =>
	request<JobDetail>(`/api/jobs/${jobId}`);

export const renameJob = (jobId: string, name: string) =>
	request<{ job_id: string; name: string }>(`/api/jobs/${jobId}/rename`, {
		method: "PUT",
		body: JSON.stringify({ name }),
	});

export const pauseJob = (jobId: string) =>
	request<{ status: string }>(`/api/jobs/${jobId}/pause`, { method: "POST" });

export const resumeJob = (jobId: string) =>
	request<{ status: string; phase: string }>(`/api/jobs/${jobId}/resume`, {
		method: "POST",
	});

export const cancelJob = (jobId: string) =>
	request<{ status: string }>(`/api/jobs/${jobId}/cancel`, { method: "POST" });

export const enqueueJob = (jobId: string) =>
	request<{ status: string; phase: string }>(`/api/jobs/${jobId}/enqueue`, {
		method: "POST",
	});

export const retryJob = (jobId: string) =>
	request<{ status: string }>(`/api/jobs/${jobId}/retry`, { method: "POST" });

export const deleteJob = (jobId: string) =>
	request<{ status: string; job_id: string }>(`/api/jobs/${jobId}`, {
		method: "DELETE",
	});

export const getJobLogs = (jobId: string) =>
	request<{ logs: string }>(`/api/jobs/${jobId}/logs`);

export const updateJobScript = (jobId: string, manualScript: string) =>
	request<{ status: string; job_id: string; manual_script: string }>(
		`/api/jobs/${jobId}/script`,
		{
			method: "POST",
			body: JSON.stringify({ manual_script: manualScript }),
		},
	);

export const uploadJobAudio = (jobId: string, file: File) =>
	uploadFile<{
		status: string;
		job_id: string;
		audio_path: string;
		size_bytes: number;
	}>(`/api/jobs/${jobId}/audio`, file);

export const getJobTTSVoice = (jobId: string) =>
	request<{
		model: string;
		voice: string;
		resolved_from: string;
		product: string;
	}>(`/api/jobs/${jobId}/tts/voice`);

export const updateJobTTSVoice = (
	jobId: string,
	body: { model?: string; voice?: string; confirm?: boolean },
) =>
	request<{
		model: string;
		voice: string;
		resolved_from: string;
		product: string;
	}>(`/api/jobs/${jobId}/tts/voice`, {
		method: "PUT",
		body: JSON.stringify(body),
	});

export const previewJobTTS = async (jobId: string) => {
	const res = await fetch(`/api/jobs/${jobId}/tts/preview`, {
		method: "POST",
	});
	if (!res.ok) {
		const text = await res.text();
		let detail = text;
		try {
			const parsed = JSON.parse(text);
			if (parsed.detail) detail = parsed.detail;
		} catch {}
		throw new Error(detail);
	}
	const blob = await res.blob();
	return URL.createObjectURL(blob);
};
