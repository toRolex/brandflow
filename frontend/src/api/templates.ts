import { request } from "./core";
import type { PreviewResponse, ScriptTemplate } from "../types/template";

export const listTemplates = () =>
	request<ScriptTemplate[]>("/api/config/templates");

export const getTemplate = (id: string) =>
	request<ScriptTemplate>(`/api/config/templates/${id}`);

export const createTemplate = (payload: ScriptTemplate) =>
	request<ScriptTemplate>("/api/config/templates", {
		method: "POST",
		body: JSON.stringify(payload),
	});

export const updateTemplate = (id: string, payload: ScriptTemplate) =>
	request<ScriptTemplate>(`/api/config/templates/${id}`, {
		method: "PUT",
		body: JSON.stringify(payload),
	});

export const deleteTemplate = (id: string) =>
	request<{ status: string }>(`/api/config/templates/${id}`, {
		method: "DELETE",
	});

export const previewTemplate = (
	id: string,
	slotContents: Record<string, string>,
	variableValues: Record<string, string>,
) =>
	request<PreviewResponse>(`/api/config/templates/${id}/preview`, {
		method: "POST",
		body: JSON.stringify({
			slot_contents: slotContents,
			variable_values: variableValues,
		}),
	});
