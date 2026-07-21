import { request } from "./core";

export const approveReview = (jobId: string, gate: string) =>
	request<{ status: string }>(`/api/reviews/${jobId}/approve`, {
		method: "POST",
		body: JSON.stringify({ review_gate: gate }),
	});

export const rejectReview = (jobId: string, gate: string) =>
	request<{ status: string }>(`/api/reviews/${jobId}/reject`, {
		method: "POST",
		body: JSON.stringify({ review_gate: gate }),
	});

export const rejectClip = (
	jobId: string,
	clipIndex: number,
	projectId?: string,
) => {
	const qs = projectId ? `?project_id=${projectId}` : "";
	return request<{ status: string }>(`/api/reviews/${jobId}/reject-clip${qs}`, {
		method: "POST",
		body: JSON.stringify({ clip_index: clipIndex }),
	});
};

export const editScript = (
	jobId: string,
	scriptText: string,
	projectId?: string,
) => {
	const qs = projectId ? `?project_id=${projectId}` : "";
	return request<{ status: string }>(`/api/reviews/${jobId}/edit-script${qs}`, {
		method: "POST",
		body: JSON.stringify({ script_text: scriptText }),
	});
};

export const regenerateWithPrompt = (
	jobId: string,
	customPrompt: string,
	projectId?: string,
) => {
	const qs = projectId ? `?project_id=${projectId}` : "";
	return request<{ status: string; result: Record<string, unknown> }>(
		`/api/reviews/${jobId}/regenerate-with-prompt${qs}`,
		{
			method: "POST",
			body: JSON.stringify({ custom_prompt: customPrompt }),
		},
	);
};
