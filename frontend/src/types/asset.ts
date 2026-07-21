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

export interface AssetStats {
	total: number;
	available: number;
	disabled: number;
	source_videos: number;
}

export interface CategoryItem {
	id: string;
	name: string;
	description: string;
}

export interface SuggestCategory {
	label: string;
	description: string;
	vision_prompt: string;
}
