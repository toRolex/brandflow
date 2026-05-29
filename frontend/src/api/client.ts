const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Projects
  listProjects: () => request<import("../types").Project[]>("/api/projects"),

  createProject: (name: string) =>
    request<import("../types").Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  getProject: (id: string) =>
    request<import("../types").Project & { jobs: import("../types").JobSummary[] }>(
      `/api/projects/${id}`
    ),

  uploadAsset: (projectId: string, file: File) =>
    uploadFile<import("../types").AssetFile>(`/api/projects/${projectId}/upload`, file),

  listAssets: (projectId: string) =>
    request<import("../types").AssetFile[]>(`/api/projects/${projectId}/assets`),

  // Asset Library
  listIndexedAssets: (projectId: string, params?: { category?: string; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set("category", params.category);
    if (params?.q) qs.set("q", params.q);
    return request<{ clips: import("../types").AssetRecord[]; stats: import("../types").AssetStats }>(
      `/api/projects/${projectId}/assets/indexed?${qs.toString()}`
    );
  },

  indexAssets: (projectId: string) =>
    request<import("../types").IndexResult>(`/api/projects/${projectId}/assets/index`, {
      method: "POST",
    }),

  updateAssetStatus: (projectId: string, assetIds: string[], status: string) =>
    request<{ updated: number }>(`/api/projects/${projectId}/assets/batch`, {
      method: "PATCH",
      body: JSON.stringify({ asset_ids: assetIds, status }),
    }),

  deleteAsset: (projectId: string, name: string) =>
    request<{ status: string }>(`/api/projects/${projectId}/assets/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  // Jobs
  createJob: (projectId: string, body: { product: string; platforms: string[]; asset?: string }) =>
    request<import("../types").JobDetail>("/api/projects/" + projectId + "/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getJob: (jobId: string) =>
    request<import("../types").JobDetail>(`/api/jobs/${jobId}`),

  pauseJob: (jobId: string) =>
    request<{ status: string }>(`/api/jobs/${jobId}/pause`, { method: "POST" }),

  retryJob: (jobId: string) =>
    request<{ status: string }>(`/api/jobs/${jobId}/retry`, { method: "POST" }),

  deleteJob: (jobId: string) =>
    request<{ status: string; job_id: string }>(`/api/jobs/${jobId}`, { method: "DELETE" }),

  getJobLogs: (jobId: string) =>
    request<{ logs: string }>(`/api/jobs/${jobId}/logs`),

  // Reviews
  approveReview: (jobId: string, gate: string) =>
    request<{ status: string }>(`/api/reviews/${jobId}/approve`, {
      method: "POST",
      body: JSON.stringify({ review_gate: gate }),
    }),

  rejectReview: (jobId: string, gate: string) =>
    request<{ status: string }>(`/api/reviews/${jobId}/reject`, {
      method: "POST",
      body: JSON.stringify({ review_gate: gate }),
    }),

  // Schedule
  getSchedule: (params?: { project_id?: string; platform?: string }) => {
    const qs = new URLSearchParams();
    if (params?.project_id) qs.set("project_id", params.project_id);
    if (params?.platform) qs.set("platform", params.platform);
    return request<import("../types").ScheduleEntry[]>(`/api/schedule?${qs.toString()}`);
  },

  exportSchedule: () => {
    window.open(`${BASE}/api/schedule/export`, "_blank");
  },

  // Config
  getConfig: () =>
    request<import("../types").ProviderConfig>("/api/config"),

  getConfigOptions: () =>
    request<import("../types").ProviderOptions>("/api/config/options"),

  saveConfig: (payload: import("../types").ProviderConfig) =>
    request<import("../types").ProviderConfig>("/api/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};
