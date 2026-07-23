import ExportTaskControls from "../../../components/ExportTaskControls";
import MediaPlayer from "../../../components/MediaPlayer";
import PhaseStatusNotice from "./PhaseStatusNotice";
import type { PanelProps } from "../types";

export default function CompletedPanel({
	exportTask,
	exportCreating,
	exportDownloading,
	onCreateExport,
	onDownloadExport,
	findArtifact,
	getPhasePresentation,
}: PanelProps) {
	const finalVideo = findArtifact("final_video");
	const presentation = getPhasePresentation("completed");
	if (presentation.kind === "integrity_error") {
		return (
			<div className="py-12">
				<h3 className="mb-2 text-lg font-semibold text-[var(--alert-red)]">完成记录不完整</h3>
				<PhaseStatusNotice presentation={presentation} />
			</div>
		);
	}
	return (
		<div className="text-center py-12">
			<div className="text-[var(--color-signal-green)] text-5xl mb-4">
				{"✓"}
			</div>
			<h3 className="text-lg font-semibold text-[var(--color-signal-green)] mb-2">
				生产完成
			</h3>
			<p className="text-[var(--text-tertiary)] text-sm mb-4">
				视频已生成并排期发布
			</p>
			<MediaPlayer src={finalVideo?.url || ""} kind="video" />
			<div className="flex flex-col items-center gap-3 mt-6">
				{exportCreating && (
					<div className="text-sm text-[var(--text-tertiary)]">正在创建...</div>
				)}

				{exportTask && !exportCreating && (
					<ExportTaskControls
						task={exportTask}
						downloading={exportDownloading}
						onDownload={onDownloadExport}
						onRecreate={onCreateExport}
					/>
				)}

				{!exportTask && !exportCreating && (
					<button
						className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-6 py-2.5 rounded-lg text-sm font-semibold hover:brightness-110 transition-all flex items-center gap-2"
						onClick={onCreateExport}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							width="16"
							height="16"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							strokeWidth="2"
							strokeLinecap="round"
							strokeLinejoin="round"
						>
							<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
							<polyline points="7 10 12 15 17 10" />
							<line x1="12" y1="15" x2="12" y2="3" />
						</svg>
						导出
					</button>
				)}
			</div>
		</div>
	);
}
