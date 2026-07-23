import type {
	Artifact,
	CoverTitle,
	Phase,
	PhaseExecutionState,
	ProductionMode,
	ReviewStrategy,
	ReviewStatus,
} from "./core";

export interface JobSummary {
	job_id: string;
	product: string;
	brand?: string;
	name?: string;
	phase: Phase;
	failed_phase?: Phase | null;
	pause_requested?: boolean;
	paused_from_phase?: Phase | null;
	cancellation_requested?: boolean;
	review_status: ReviewStatus;
	execution?: PhaseExecutionState;
	phase_index: number;
	phase_total: number;
	last_error?: string;
	manual_script?: string;
	uploaded_audio_path?: string;
	audio_source?: string;
	display_index?: string;
	skip_subtitle?: boolean;
	auto_approve?: boolean;
	asset_review_unresolved_count?: number | null;
	review_strategy?: ReviewStrategy;
	mode?: ProductionMode;
	artifacts?: Artifact[];
	pending_unresolved_count?: number;
}

export interface JobDetail {
	job_id: string;
	project_id: string;
	product: string;
	brand?: string;
	name?: string;
	platforms: string[];
	phase: Phase;
	failed_phase?: Phase | null;
	pause_requested?: boolean;
	paused_from_phase?: Phase | null;
	cancellation_requested?: boolean;
	review_status: ReviewStatus;
	execution: PhaseExecutionState;
	artifacts: Artifact[];
	last_error?: string;
	logs?: string;
	manual_script?: string;
	uploaded_audio_path?: string;
	audio_source?: string;
	cover_title?: CoverTitle | null;
	mode?: ProductionMode;
	review_strategy?: ReviewStrategy;
	tts_model?: string;
	tts_voice?: string;
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
}

export interface BatchCreateRequest {
	platforms: string[];
	review_strategy?: ReviewStrategy;
	jobs: BatchJobItem[];
}

export interface BatchCreateResponse {
	product: string;
	platforms: string[];
	review_strategy: ReviewStrategy;
	count: number;
	results: Array<{
		job_id: string;
		display_index: string;
		product: string;
		name: string;
		phase: string;
		skip_subtitle: boolean;
		mode?: ProductionMode;
		review_strategy?: ReviewStrategy;
	}>;
}

export interface SceneFolder {
	name: string;
	path: string;
}
