import type { Project, ProjectPage } from "../types/project";
import { DEFAULT_PAGE_SIZE, request } from "./core";

export const listProjects = (page = 1, pageSize = DEFAULT_PAGE_SIZE) =>
	request<ProjectPage>(`/api/projects?page=${page}&page_size=${pageSize}`);

export const createProject = (name: string) =>
	request<Project>("/api/projects", {
		method: "POST",
		body: JSON.stringify({ name }),
	});

export const getProject = (id: string) =>
	request<Project>(`/api/projects/${id}`);

export const deleteProject = (id: string) =>
	request<{ ok: boolean }>(`/api/projects/${id}`, { method: "DELETE" });

export const toggleProjectPin = (id: string) =>
	request<{ id: string; is_pinned: boolean; pinned_at: string }>(
		`/api/projects/${id}/pin`,
		{ method: "POST" },
	);
