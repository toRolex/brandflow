import { request } from "./core";

export const generateCoverTitle = (body: {
	script_text: string;
	product?: string;
	brand?: string;
}) =>
	request<{ text: string; highlight_words: string[] }>(
		"/api/cover-title/generate",
		{
			method: "POST",
			body: JSON.stringify(body),
		},
	);
