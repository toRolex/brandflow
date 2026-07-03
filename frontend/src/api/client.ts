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

  deleteProject: (id: string) =>
    request<{ ok: boolean }>(`/api/projects/${id}`, { method: "DELETE" }),

  uploadAsset: (projectId: string, file: File) =>
    uploadFile<import("../types").AssetFile>(`/api/projects/${projectId}/upload`, file),

  listAssets: (projectId: string) =>
    request<import("../types").AssetFile[]>(`/api/projects/${projectId}/assets`),

  // Asset Library
  listIndexedAssets: async (projectId: string, params?: { category?: string; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set("category", params.category);
    if (params?.q) qs.set("q", params.q);
    const res = await request<{
      assets: import("../types").AssetRecord[];
      stats: {
        total_clips: number;
        available_clips: number;
        disabled_clips: number;
        source_videos: number;
      };
    }>(`/api/projects/${projectId}/assets/indexed?${qs.toString()}`);
    return {
      assets: res.assets,
      stats: {
        total: res.stats.total_clips,
        available: res.stats.available_clips,
        disabled: res.stats.disabled_clips,
        source_videos: res.stats.source_videos,
      },
    };
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

  // Shared Asset Library (global, cross-project)
  uploadAssetShared: (file: File) =>
    uploadFile<import("../types").AssetFile>("/api/assets/upload", file),

  listIndexedAssetsShared: async (params?: { category?: string; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set("category", params.category);
    if (params?.q) qs.set("q", params.q);
    const res = await request<{
      assets: import("../types").AssetRecord[];
      stats: {
        total_clips: number;
        available_clips: number;
        disabled_clips: number;
        source_videos: number;
      };
    }>(`/api/assets/indexed?${qs.toString()}`);
    return {
      assets: res.assets,
      stats: {
        total: res.stats.total_clips,
        available: res.stats.available_clips,
        disabled: res.stats.disabled_clips,
        source_videos: res.stats.source_videos,
      },
    };
  },

  indexAssetsShared: () =>
    request<import("../types").IndexResult>("/api/assets/index", { method: "POST" }),

  indexAssetsSharedAsync: () =>
    request<{ task_id: string; total_videos: number }>("/api/assets/index?async_mode=true", { method: "POST" }),

  getIndexStatus: (taskId: string) =>
    request<import("../types").IndexTaskState>(`/api/assets/index/${taskId}/status`),

  getIndexLogsUrl: (taskId: string) => `/api/assets/index/${taskId}/logs`,

  updateAssetStatusShared: (assetIds: string[], status: string) =>
    request<{ updated: number }>("/api/assets/batch", {
      method: "PATCH",
      body: JSON.stringify({ asset_ids: assetIds, status }),
    }),

  updateAssetFields: (assetId: string, fields: { product?: string; category?: string }) =>
    request<{ updated: number }>(`/api/assets/${assetId}/fields`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    }),

  batchUpdateAssetFields: (assetIds: string[], fields: { product?: string; category?: string }) =>
    request<{ updated: number }>("/api/assets/batch-fields", {
      method: "PATCH",
      body: JSON.stringify({ asset_ids: assetIds, ...fields }),
    }),

  deleteAssetShared: (assetId: string) =>
    request<{ status: string }>(`/api/assets/${assetId}`, {
      method: "DELETE",
    }),

  batchDeleteAssets: (assetIds: string[]) =>
    request<{ deleted: number; files_deleted: number }>("/api/assets/batch", {
      method: "DELETE",
      body: JSON.stringify({ asset_ids: assetIds }),
    }),

  migrateAssets: () =>
    request<{ migrated_projects: number; migrated_clips: number; migrated_sources: number }>(
      "/api/assets/migrate",
      { method: "POST" },
    ),

  // Jobs
  createJob: (projectId: string, body: { product: string; brand?: string; platforms: string[]; name?: string; mode?: import("../types").ProductionMode; manual_script?: string; skip_subtitle?: boolean; auto_approve?: boolean; audio_source?: string; music_track_path?: string; music_volume?: number; language?: string; cover_title?: { text: string; highlight_words?: string[] } | null }) =>
    request<import("../types").JobDetail>("/api/projects/" + projectId + "/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  batchCreateJobs: (projectId: string, body: import("../types").BatchCreateRequest) =>
    request<import("../types").BatchCreateResponse>(`/api/projects/${projectId}/jobs/batch`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getJob: (jobId: string) =>
    request<import("../types").JobDetail>(`/api/jobs/${jobId}`),

  renameJob: (jobId: string, name: string) =>
    request<{ job_id: string; name: string }>(`/api/jobs/${jobId}/rename`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    }),

  pauseJob: (jobId: string) =>
    request<{ status: string }>(`/api/jobs/${jobId}/pause`, { method: "POST" }),

  retryJob: (jobId: string) =>
    request<{ status: string }>(`/api/jobs/${jobId}/retry`, { method: "POST" }),

  deleteJob: (jobId: string) =>
    request<{ status: string; job_id: string }>(`/api/jobs/${jobId}`, { method: "DELETE" }),

  getJobLogs: (jobId: string) =>
    request<{ logs: string }>(`/api/jobs/${jobId}/logs`),

  updateJobScript: (jobId: string, manual_script: string) =>
    request<{ status: string; job_id: string; manual_script: string }>(`/api/jobs/${jobId}/script`, {
      method: "POST",
      body: JSON.stringify({ manual_script }),
    }),

  uploadJobAudio: (jobId: string, file: File) =>
    uploadFile<{ status: string; job_id: string; audio_path: string; size_bytes: number }>(
      `/api/jobs/${jobId}/audio`,
      file
    ),

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

  rejectClip: (jobId: string, clipIndex: number, projectId?: string) => {
    const qs = projectId ? `?project_id=${projectId}` : "";
    return request<{ status: string }>(`/api/reviews/${jobId}/reject-clip${qs}`, {
      method: "POST",
      body: JSON.stringify({ clip_index: clipIndex }),
    });
  },

  editScript: (jobId: string, scriptText: string, projectId?: string) => {
    const qs = projectId ? `?project_id=${projectId}` : "";
    return request<{ status: string }>(`/api/reviews/${jobId}/edit-script${qs}`, {
      method: "POST",
      body: JSON.stringify({ script_text: scriptText }),
    });
  },

  regenerateWithPrompt: (jobId: string, customPrompt: string, projectId?: string) => {
    const qs = projectId ? `?project_id=${projectId}` : "";
    return request<{ status: string; result: Record<string, unknown> }>(
      `/api/reviews/${jobId}/regenerate-with-prompt${qs}`,
      {
        method: "POST",
        body: JSON.stringify({ custom_prompt: customPrompt }),
      }
    );
  },

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

  // Product Config
  getProductConfig: () =>
    request<import("../types").ProductConfig>("/api/config/product"),

  saveProductConfig: (payload: import("../types").ProductConfig) =>
    request<import("../types").ProductConfig>("/api/config/product", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  resetProductConfig: () =>
    request<{ status: string }>("/api/config/product", {
      method: "DELETE",
    }),

  // TTS
  getTTSConfig: (projectId?: string) =>
    request<Record<string, unknown>>(`/api/tts/config${projectId ? `?project_id=${projectId}` : ""}`),

  saveTTSConfig: (config: Record<string, unknown>, projectId?: string) =>
    request<{ success: boolean }>(`/api/tts/config${projectId ? `?project_id=${projectId}` : ""}`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  getTTSVoices: (provider?: string) =>
    request<{ preset_voices: Array<{ id: string; label: string; note: string }> }>(
      `/api/tts/voices${provider ? `?provider=${provider}` : ""}`
    ),

  previewTTS: async (requestBody: { text: string; model?: string; voice?: string; style_prompt?: string; voice_design_prompt?: string; instructions?: string; optimize_instructions?: boolean; language_type?: string }) => {
    const res = await fetch("/api/tts/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status}: ${text}`);
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },

  getTTSMetrics: (projectId?: string, range?: string) => {
    const qs = new URLSearchParams();
    if (projectId) qs.set("project_id", projectId);
    if (range) qs.set("range", range);
    return request<Record<string, unknown>>(`/api/tts/metrics?${qs.toString()}`);
  },

  getTTSLogs: (params?: { project_id?: string; limit?: number; offset?: number; status?: string }) => {
    const qs = new URLSearchParams();
    if (params?.project_id) qs.set("project_id", params.project_id);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    if (params?.status) qs.set("status", params.status);
    return request<Array<Record<string, unknown>>>(`/api/tts/logs?${qs.toString()}`);
  },

  // Music Library
  listMusic: () =>
    request<{ tracks: import("../types").MusicTrack[] }>("/api/music"),

  // Cover Title
  generateCoverTitle: (body: { script_text: string; product?: string; brand?: string }) =>
    request<{ text: string; highlight_words: string[] }>("/api/cover-title/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Metrics / Analytics
  uploadMetrics: (file: File) =>
    uploadFile<import("../types").ImportResult>("/api/metrics/upload", file),

  scanMetrics: () =>
    request<import("../types").ScanResult>("/api/metrics/scan", { method: "POST" }),

  getMetricsOverview: (days: number = 7, platform?: string) => {
    const qs = new URLSearchParams();
    qs.set("days", String(days));
    if (platform) qs.set("platform", platform);
    return request<import("../types").MetricsOverview>(`/api/metrics/overview?${qs.toString()}`);
  },

  getMetricsVideos: (params?: {
    sort_by?: string;
    platform?: string;
    search?: string;
    page?: number;
    page_size?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.sort_by) qs.set("sort_by", params.sort_by);
    if (params?.platform) qs.set("platform", params.platform);
    if (params?.search) qs.set("search", params.search);
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    return request<import("../types").VideoMetricPage>(`/api/metrics/videos?${qs.toString()}`);
  },

  getMetricsTopics: (days: number = 30, platform?: string, limit: number = 10) => {
    const qs = new URLSearchParams();
    qs.set("days", String(days));
    if (platform) qs.set("platform", platform);
    qs.set("limit", String(limit));
    return request<import("../types").TopicStat[]>(`/api/metrics/topics?${qs.toString()}`);
  },

  // Scene folders
  getSceneFolders: () =>
    request<import("../types").SceneFoldersResponse>("/api/scene/folders"),

  // Scene upload
  uploadSceneVideo: async (folderName: string, file: File) => {
    const form = new FormData();
    form.append("folder", folderName);
    form.append("file", file);
    const res = await fetch("/api/scene/upload", { method: "POST", body: form });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status}: ${text}`);
    }
    return res.json();
  },

  // Scene folder files
  getSceneFolderFiles: (folderName: string) =>
    request<import("../types").SceneFolderFilesResponse>(
      `/api/scene/folders/${encodeURIComponent(folderName)}/files`
    ),

  // Delete scene file
  deleteSceneFile: (folderName: string, fileName: string) =>
    request<{ status: string }>(
      `/api/scene/folders/${encodeURIComponent(folderName)}/files/${encodeURIComponent(fileName)}`,
      { method: "DELETE" }
    ),

  // Categories
  listCategories: () =>
    request<import("../types").CategoryItem[]>("/api/assets/categories"),

  suggestCategories: () =>
    request<{ suggestions: import("../types").SuggestCategory[] }>(
      "/api/assets/categories/suggest",
      { method: "POST" }
    ),

  // Export download (returns blob)
  downloadExport: async (jobId: string) => {
    const res = await fetch(`/api/jobs/${jobId}/export`);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status}: ${text}`);
    }
    return res.blob();
  },
};
