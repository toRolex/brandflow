import type { Phase, ProductionMode } from "../types";
import { PIPELINE_STEPS } from "../types";

interface Props {
	currentPhase: Phase;
	completedPhases: Phase[];
	onStepClick: (key: string) => void;
	activeStepKey: string;
	jobInfo?: string;
	mode?: ProductionMode;
	onPause?: () => void;
	onRetry?: () => void;
	onViewLogs?: () => void;
}

const IMPORT_HIDE_PHASES: Set<string> = new Set([
	"script_review",
	"tts_review",
]);

export default function PipelineSidebar({
	currentPhase,
	completedPhases,
	onStepClick,
	activeStepKey,
	jobInfo,
	mode,
	onPause,
	onRetry,
	onViewLogs,
}: Props) {
	return (
		<div className="w-52 bg-[var(--bg-page)] border-r border-[var(--border-default)] p-3 flex-shrink-0 overflow-y-auto">
			{jobInfo && (
				<div className="text-xs font-semibold text-[var(--text-secondary)] mb-3">
					{jobInfo}
				</div>
			)}
			<div className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wide mb-3">
				流水线步骤
			</div>
			{PIPELINE_STEPS.filter((step) => {
				const terminalPhases: Phase[] = [
					"completed",
					"failed",
					"cancelled",
					"paused",
				];
				if (
					terminalPhases.includes(step.phase) &&
					step.phase !== currentPhase
				) {
					return false;
				}
				if (mode === "import" && IMPORT_HIDE_PHASES.has(step.phase)) {
					return false;
				}
				return true;
			}).map((step) => {
				const stepNum = PIPELINE_STEPS.indexOf(step) + 1;
				const done = completedPhases.includes(step.phase);
				const active = step.key === activeStepKey;
				const isReview = step.isReview;

				return (
					<button
						key={step.key}
						onClick={() => onStepClick(step.key)}
						className={`flex items-center gap-1.5 w-full text-left px-1.5 py-1.5 rounded-md mb-0.5 text-xs transition-colors ${
							active
								? isReview
									? "bg-[var(--color-caution-amber)] text-[var(--text-primary)] font-semibold"
									: "bg-[var(--btn-primary-bg)] text-white"
								: done
									? "bg-[var(--btn-primary-bg)] text-white"
									: "text-[var(--text-secondary)]"
						}`}
					>
						<span
							className={`w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10px] flex-shrink-0 ${
								done
									? "bg-white text-[var(--text-link)] font-bold"
									: active
										? "bg-white text-[var(--text-primary)] font-bold"
										: "border-1.5 border-[var(--border-default)] text-[var(--text-secondary)]"
							}`}
						>
							{done ? "\u2713" : active ? "!" : stepNum}
						</span>
						{step.label}
					</button>
				);
			})}
			<div className="mt-4 pt-3 border-t border-gray-200">
				<button
					className="w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 rounded-md mb-1 transition-colors"
					onClick={onPause}
				>
					{"\u23F8"} 暂停
				</button>
				<button
					className="w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 rounded-md mb-1 transition-colors"
					onClick={onRetry}
				>
					{"\u21BB"} 重试当前
				</button>
				<button
					className="w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 rounded-md transition-colors"
					onClick={onViewLogs}
				>
					{"\uD83D\uDCCB"} 查看日志
				</button>
			</div>
		</div>
	);
}
