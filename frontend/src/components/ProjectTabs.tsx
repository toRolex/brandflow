import type { JobSummary } from "../types";
import JobTable from "./JobTable";

type TabKey = "jobs";

interface ProjectTabsProps {
	tab: TabKey;
	onTabChange: (tab: TabKey) => void;
	jobs: JobSummary[];
	selectedJobIds: Set<string>;
	onSelectionChange: (ids: Set<string>) => void;
	onRetry: (jobId: string) => void;
	onDeleteJob: (jobId: string) => void;
	onRenameJob: (jobId: string, name: string) => Promise<void>;
}

export default function ProjectTabs({
	jobs,
	selectedJobIds,
	onSelectionChange,
	onRetry,
	onDeleteJob,
	onRenameJob,
}: ProjectTabsProps) {
	return (
		<>
			<JobTable
				jobs={jobs}
				onRetry={onRetry}
				onDelete={onDeleteJob}
				onRename={onRenameJob}
				selectedJobIds={selectedJobIds}
				onSelectionChange={onSelectionChange}
			/>
		</>
	);
}
