export type Phase =
  | "queued" | "script_generating" | "script_review"
  | "tts_generating" | "subtitle_generating" | "asset_retrieving"
  | "asset_review" | "video_rendering" | "final_review"
  | "schedule_writing" | "completed" | "failed" | "cancelled" | "paused";

export type ReviewStatus = "none" | "pending" | "approved" | "rejected" | "overridden";

export interface Project {
  id: string;
  name: string;
  status: string;
  job_count: number;
}

export interface JobSummary {
  job_id: string;
  product: string;
  phase: Phase;
  review_status: ReviewStatus;
  phase_index: number;
  phase_total: number;
  last_error?: string;
}

export interface AssetFile {
  name: string;
  size_bytes: number;
  duration_seconds?: number;
  resolution?: string;
  in_use: boolean;
}

export interface Artifact {
  kind: string;
  relative_path: string;
  url: string;
}

export interface JobDetail {
  job_id: string;
  project_id: string;
  product: string;
  platforms: string[];
  phase: Phase;
  review_status: ReviewStatus;
  artifacts: Artifact[];
  last_error?: string;
  logs?: string;
}

export interface ScriptCheckResult {
  length: number;
  brand_name_count: number;
  product_name_count: number;
  has_safety_warning: boolean;
  has_emoji: boolean;
  forbidden_terms: string[];
  passed: boolean;
}

export interface ScheduleEntry {
  id: number;
  job_id: string;
  platform: string;
  title: string;
  description: string;
  status: "pending" | "published";
  created_at: string;
}

export interface ProviderSection {
  selected: string;
  providers: Record<string, Record<string, unknown>>;
}

export interface ProviderConfig {
  providers: Record<string, ProviderSection>;
}

export interface ProviderField {
  name: string;
  label: string;
  kind: string;
  secret?: boolean;
  options?: string[];
}

export interface ProviderOption {
  label: string;
  fields: ProviderField[];
}

export interface ProviderOptions {
  providers: Record<string, {
    providers: Record<string, ProviderOption>;
  }>;
}

export interface PipelineStep {
  key: string;    // unique identifier for UI rendering
  phase: Phase;   // backend phase value
  label: string;
  isReview: boolean;
}

export const PIPELINE_STEPS: PipelineStep[] = [
  { key: "asset_upload", phase: "asset_retrieving", label: "上传素材", isReview: false },
  { key: "script_gen", phase: "script_generating", label: "生成脚本", isReview: false },
  { key: "script_review", phase: "script_review", label: "脚本审核", isReview: true },
  { key: "packaging", phase: "script_generating", label: "生成包装", isReview: false },
  { key: "tts", phase: "tts_generating", label: "TTS 配音", isReview: false },
  { key: "subtitle", phase: "subtitle_generating", label: "转录字幕", isReview: false },
  { key: "video_base", phase: "video_rendering", label: "底包拼接", isReview: false },
  { key: "asset_review", phase: "asset_review", label: "素材审核", isReview: true },
  { key: "final_review", phase: "final_review", label: "封面·烧录", isReview: true },
  { key: "schedule", phase: "schedule_writing", label: "排期发布", isReview: false },
];
