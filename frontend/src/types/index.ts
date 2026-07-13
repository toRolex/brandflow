export type ProductionMode = "import" | "generate";

export type Phase =
  | "queued" | "script_generating" | "script_review"
  | "tts_generating" | "tts_review" | "subtitle_generating" | "asset_retrieving"
  | "asset_review"
  | "video_rendering" | "final_review"
  | "schedule_writing" | "scene_assembling" | "montage_assembling"
  | "completed" | "failed" | "cancelled" | "paused";

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
  brand?: string;
  name?: string;
  phase: Phase;
  review_status: ReviewStatus;
  phase_index: number;
  phase_total: number;
  last_error?: string;
  manual_script?: string;
  uploaded_audio_path?: string;
  audio_source?: string;
  display_index?: string;
  skip_subtitle?: boolean;
  auto_approve?: boolean;
  mode?: ProductionMode;
  artifacts?: Artifact[];
}

export interface AssetFile {
  name: string;
  size_bytes: number;
  duration_seconds?: number;
  resolution?: string;
  in_use: boolean;
}

export type AssetCategory = string;

export interface AssetRecord {
  asset_id: string;
  file_path: string;
  category: AssetCategory;
  product: string;
  confidence: number;
  duration_seconds: number;
  status: "available" | "disabled" | "pending_review" | "classification_failed";
  usage_count: number;
  source_video: string;
  tags: string[];
  created_at: string;
  last_used_at: string;
}

export interface AssetFilters {
  product: string;
  category: string;
  status: string;
  keyword: string;
  durationMin: number;
  durationMax: number;
  confidenceMin: number;
  confidenceMax: number;
  usageMin: number;
  usageMax: number;
}

export interface CategoryItem {
  id: string;
  name: string;
  description: string;
}

export type IndexStatus = "idle" | "processing" | "done";

export interface IndexResult {
  indexed: number;
  skipped: number;
  total_clips: number;
}

export interface AssetStats {
  total: number;
  available: number;
  disabled: number;
  source_videos: number;
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
  brand?: string;
  name?: string;
  platforms: string[];
  phase: Phase;
  review_status: ReviewStatus;
  artifacts: Artifact[];
  last_error?: string;
  logs?: string;
  manual_script?: string;
  uploaded_audio_path?: string;
  audio_source?: string;
  cover_title?: CoverTitle | null;
  mode?: ProductionMode;
  tts_model?: string;
  tts_voice?: string;
}

export interface CoverTitle {
  text: string;
  highlight_words?: string[];
  style?: {
    primary_color?: string;
    outline_color?: string;
    highlight_color?: string;
    outline_width?: number;
    position?: string;
  };
}

export interface BatchJobItem {
  name: string;
  manual_script: string;
  skip_subtitle: boolean;
  mode?: ProductionMode;
  audio_source?: string;
  music_track_path?: string;
  music_volume?: number;
  language?: string;
  cover_title?: CoverTitle | null;
  tts_model?: string;
  tts_voice?: string;
}

export interface BatchCreateRequest {
  product: string;
  brand?: string;
  platforms: string[];
  auto_approve?: boolean;
  jobs: BatchJobItem[];
}

export interface BatchCreateResponse {
  product: string;
  platforms: string[];
  auto_approve: boolean;
  count: number;
  results: Array<{
    job_id: string;
    display_index: string;
    product: string;
    name: string;
    phase: string;
    skip_subtitle: boolean;
    auto_approve: boolean;
  }>;
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

export type IndexTaskStatus = "pending" | "running" | "completed" | "failed";

export interface IndexTaskState {
  task_id: string;
  status: IndexTaskStatus;
  progress: number;
  current_step: string;
  current_video: number;
  total_videos: number;
  error: string | null;
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
  { key: "queued", phase: "queued", label: "排队中", isReview: false },
  { key: "script_gen", phase: "script_generating", label: "生成脚本", isReview: false },
  { key: "script_review", phase: "script_review", label: "脚本审核", isReview: true },
  { key: "tts", phase: "tts_generating", label: "TTS 配音", isReview: false },
  { key: "tts_review", phase: "tts_review", label: "TTS 审核", isReview: true },
  { key: "subtitle", phase: "subtitle_generating", label: "转录字幕", isReview: false },
  { key: "asset_retrieving", phase: "asset_retrieving", label: "素材检索", isReview: false },
  { key: "asset_review", phase: "asset_review", label: "素材审核", isReview: true },
  { key: "video_base", phase: "video_rendering", label: "底包拼接", isReview: false },
  { key: "final_review", phase: "final_review", label: "终审·烧录", isReview: true },
  { key: "completed", phase: "completed", label: "已完成", isReview: false },
  { key: "failed", phase: "failed", label: "已失败", isReview: false },
  { key: "cancelled", phase: "cancelled", label: "已取消", isReview: false },
  { key: "paused", phase: "paused", label: "已暂停", isReview: false },
];

export interface ProductConfig {
  default_name: string;
  default_brand: string;
  script: {
    scene: string;
    material: string;
    system_prompt: string;
    word_count_min?: number;
    word_count_max?: number;
    forbidden_words?: string[];
    emoji_forbidden?: boolean;
    product_name_count?: number;
    brand_name_count?: number;
    [key: string]: unknown;
  };
  categories?: CategoryConfig[];
  [key: string]: unknown;
}

export interface CategoryConfig {
  id: string;
  name: string;
  description: string;
  vision_prompt: string;
}

export interface SuggestCategory {
  label: string;
  description: string;
  vision_prompt: string;
}

export interface MusicTrack {
  filename: string;
  relative_path: string;
  duration_seconds: number | null;
  size_bytes: number;
}

// ── Scene Upload ───────────────────────────────────

export interface SceneFolder {
  name: string;
  file_count: number;
}

export interface SceneFolderFile {
  name: string;
  size_bytes: number;
}

export interface SceneFoldersResponse {
  folders: SceneFolder[];
}

export interface SceneFolderFilesResponse {
  files: SceneFolderFile[];
}

// ── Script Template ────────────────────────────────

export type SlotType = "hook" | "selling_point" | "usage_scene" | "call_to_action";
export type VariableSource = "manual" | "product_config" | "knowledge_base";

export interface TemplateSlot {
  type: SlotType;
  label: string;
  required: boolean;
  max_length: number;
  hint: string;
}

export interface TemplateVariable {
  name: string;
  label: string;
  source: VariableSource;
}

export interface ScriptTemplate {
  id: string;
  name: string;
  description: string;
  slots: TemplateSlot[];
  variables: TemplateVariable[];
  default_config_override: Record<string, unknown>;
}

export interface PreviewResponse {
  rendered_script: string;
}

export interface MetricsOverview {
  total_plays: number;
  total_likes: number;
  total_followers: number;
  avg_completion: number;
  video_count: number;
  daily: DailyMetric[];
}

export interface DailyMetric {
  publish_date: string;
  plays: number;
  likes: number;
  followers: number;
  avg_completion: number | null;
}

export interface VideoMetric {
  id: number;
  platform: "weixin" | "xiaohongshu";
  title: string;
  platform_id: string | null;
  publish_date: string;
  content_type: string;
  plays: number;
  likes: number;
  comments: number;
  shares: number;
  followers_gained: number;
  completion_rate: number | null;
  avg_watch_duration: number | null;
  exposure: number;
  cover_click_rate: number | null;
  favorites: number;
  danmaku: number;
  forward_count: number;
  job_id: string | null;
  used_asset_ids: string[];
}

export interface VideoMetricPage {
  items: VideoMetric[];
  total: number;
  page: number;
  page_size: number;
}

export interface TopicStat {
  keyword: string;
  total_plays: number;
  video_count: number;
  avg_completion: number;
}

export interface ImportResult {
  inserted: number;
  updated: number;
  error?: string;
}

export interface ScanResult {
  files_processed: number;
  inserted: number;
  updated: number;
}

