import { request } from "./core";

export const getTTSConfig = (productId?: string) =>
	request<Record<string, unknown>>(
		`/api/tts/config${productId ? `?product_id=${productId}` : ""}`,
	);

export const saveTTSConfig = (
	config: Record<string, unknown>,
	productId?: string,
) =>
	request<{ success: boolean }>(
		`/api/tts/config${productId ? `?product_id=${productId}` : ""}`,
		{
			method: "PUT",
			body: JSON.stringify(config),
		},
	);

export const getTTSVoices = (provider?: string, model?: string) => {
	const params = new URLSearchParams();
	if (provider) params.set("provider", provider);
	if (model) params.set("model", model);
	const qs = params.toString();
	return request<{
		preset_voices: Array<{
			id: string;
			label: string;
			note: string;
			model: string;
		}>;
	}>(`/api/tts/voices${qs ? `?${qs}` : ""}`);
};

export const previewTTS = async (requestBody: {
	text: string;
	model?: string;
	voice?: string;
	style_prompt?: string;
	voice_design_prompt?: string;
	instructions?: string;
	optimize_instructions?: boolean;
	language_type?: string;
}) => {
	const res = await fetch("/api/tts/preview", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(requestBody),
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
