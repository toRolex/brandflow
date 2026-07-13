import type { JobSummary, ScheduleEntry } from "../types";
import JobTable from "./JobTable";
import ScheduleTable from "./ScheduleTable";
import SceneUpload from "./SceneUpload";

type TabKey = "jobs" | "schedule" | "scene";

interface ProjectTabsProps {
  tab: TabKey;
  onTabChange: (tab: TabKey) => void;
  jobs: JobSummary[];
  schedule: ScheduleEntry[];
  selectedJobIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
  onRetry: (jobId: string) => void;
  onDeleteJob: (jobId: string) => void;
  onRenameJob: (jobId: string, name: string) => Promise<void>;
  onExportSchedule: () => Promise<void>;
}

const TABS: { key: TabKey; label: string }[] = [
  { key: "jobs", label: "Job 列表" },
  { key: "schedule", label: "排期池" },
  { key: "scene", label: "场景素材" },
];

export default function ProjectTabs({
  tab,
  onTabChange,
  jobs,
  schedule,
  selectedJobIds,
  onSelectionChange,
  onRetry,
  onDeleteJob,
  onRenameJob,
  onExportSchedule,
}: ProjectTabsProps) {
  return (
    <>
      {/* tab nav */}
      <div className="flex gap-4 border-b mb-4" style={{ borderColor: "var(--border-default)" }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`pb-2 text-sm font-medium transition-colors ${
              tab === t.key ? "border-b-2" : ""
            }`}
            style={
              tab === t.key
                ? { color: "var(--accent)", borderColor: "var(--accent)" }
                : { color: "var(--text-secondary)" }
            }
            onClick={() => onTabChange(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* tab content */}
      {tab === "jobs" ? (
        <JobTable
          jobs={jobs}
          onRetry={onRetry}
          onDelete={onDeleteJob}
          onRename={onRenameJob}
          selectedJobIds={selectedJobIds}
          onSelectionChange={onSelectionChange}
        />
      ) : tab === "schedule" ? (
        <ScheduleTable entries={schedule} onExport={onExportSchedule} />
      ) : (
        <SceneUpload />
      )}
    </>
  );
}
