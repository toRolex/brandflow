export interface Project {
	id: string;
	name: string;
	status: string;
	job_count: number;
}

export interface ProjectPage {
	items: Project[];
	total: number;
	page: number;
	page_size: number;
}

export interface JobSummaryPage {
	items: import("./job").JobSummary[];
	total: number;
	page: number;
	page_size: number;
}
