import type { ExportTaskState } from "../types";

interface ExportTaskControlsProps {
	task: ExportTaskState;
	downloading: boolean;
	onDownload: () => void;
	onRecreate: () => void;
}

function DownloadIcon() {
	return (
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
	);
}

function ProcessingButton() {
	return (
		<button
			className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-6 py-2.5 rounded-lg text-sm font-semibold opacity-50 cursor-not-allowed flex items-center gap-2"
			disabled={true}
		>
			<DownloadIcon />
			处理中...
		</button>
	);
}

export default function ExportTaskControls({
	task,
	downloading,
	onDownload,
	onRecreate,
}: ExportTaskControlsProps) {
	switch (task.status) {
		case "queued":
			return (
				<>
					<div className="text-sm text-[var(--text-tertiary)]">排队中...</div>
					<ProcessingButton />
				</>
			);
		case "running":
			return (
				<>
					<div className="flex items-center gap-2 w-full max-w-xs">
						<div className="flex-1 bg-[var(--border-color)] rounded-full h-2 overflow-hidden">
							<div
								role="progressbar"
								aria-valuemin={0}
								aria-valuemax={100}
								aria-valuenow={task.progress || 0}
								className="bg-[var(--color-signal-green)] h-full rounded-full transition-all duration-500"
								style={{ width: `${task.progress || 0}%` }}
							/>
						</div>
						<span className="text-xs text-[var(--text-tertiary)] min-w-[3ch] text-right">
							{task.progress || 0}%
						</span>
					</div>
					<ProcessingButton />
				</>
			);
		case "ready":
			return (
				<button
					className="bg-[var(--color-signal-green)] text-white border-none px-6 py-2.5 rounded-lg text-sm font-semibold hover:brightness-110 transition-all flex items-center gap-2"
					onClick={onDownload}
					disabled={downloading}
				>
					<DownloadIcon />
					{downloading ? "下载中..." : "下载导出包"}
				</button>
			);
		case "failed":
			return (
				<>
					<div className="text-sm text-[var(--alert-red)] bg-[var(--alert-red-bg)] px-3 py-1.5 rounded-md max-w-sm text-center">
						{task.error || "导出失败"}
					</div>
					<button
						className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-6 py-2.5 rounded-lg text-sm font-semibold hover:brightness-110 transition-all flex items-center gap-2"
						onClick={onRecreate}
					>
						重新创建
					</button>
				</>
			);
		case "stale":
			return (
				<>
					<div className="text-sm text-[var(--text-tertiary)]">
						导出包已过期（视频已重新渲染）
					</div>
					<button
						className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-6 py-2.5 rounded-lg text-sm font-semibold hover:brightness-110 transition-all flex items-center gap-2"
						onClick={onRecreate}
					>
						重新创建
					</button>
				</>
			);
	}
}
