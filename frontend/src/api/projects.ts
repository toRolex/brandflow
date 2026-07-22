import type { Project } from "../types/project";
import { request } from "./core";

export const listProjects = () => request<Project[]>("/api/projects");

export const createProject = (name: string) =>
	request<Project>("/api/projects", {
		method: "POST",
		body: JSON.stringify({ name }),
	});

export const getProject = (id: string) =>
	request<Project & { jobs: import("../types/job").JobSummary[] }>(
		`/api/projects/${id}`,
	);

export const deleteProject = (id: string) =>
	request<{ ok: boolean }>(`/api/projects/${id}`, { method: "DELETE" });
