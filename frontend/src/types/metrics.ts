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
