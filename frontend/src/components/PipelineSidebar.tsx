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

const IMPORT_HIDE_PHASES: ReadonlySet<Phase> = new Set([
	"script_generating",
	"script_review",
	"tts_review",
]);

const GENERATE_HIDE_PHASES: ReadonlySet<Phase> = new Set(["scene_assembling"]);

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
	const terminalPhases: ReadonlySet<Phase> = new Set([
		"completed",
		"failed",
		"cancelled",
		"paused",
	]);
	const visibleSteps = PIPELINE_STEPS.filter((step) => {
		if (terminalPhases.has(step.phase) && step.phase !== currentPhase) {
			return false;
		}
		if (
			step.phase === "migration_required" &&
			currentPhase !== "migration_required"
		) {
			return false;
		}
		if (mode === "import" && IMPORT_HIDE_PHASES.has(step.phase)) {
			return false;
		}
		if (mode === "generate" && GENERATE_HIDE_PHASES.has(step.phase)) {
			return false;
		}
		return true;
	});

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
			{visibleSteps.map((step, index) => {
				const stepNum = index + 1;
				const done = completedPhases.includes(step.phase);
				const active = step.key === activeStepKey;
				const isReview = step.isReview;
				const isOperableReview =
					active && isReview && step.phase === currentPhase;
				const isViewOnlyReview =
					active && isReview && step.phase !== currentPhase;

				return (
					<button
						key={step.key}
						onClick={() => onStepClick(step.key)}
						aria-current={active ? "step" : undefined}
						title={
							isViewOnlyReview ? "当前不在该审核阶段，无法操作" : undefined
						}
						className={`flex items-center gap-1.5 w-full text-left px-1.5 py-1.5 rounded-md mb-0.5 text-xs transition-colors ${
							active
								? isOperableReview
									? "bg-[var(--color-caution-amber)] text-[var(--text-primary)] font-semibold"
									: isViewOnlyReview
										? "border border-[var(--color-caution-amber)] text-[var(--text-primary)] bg-[var(--bg-table-head)]"
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
							{done ? "✓" : active ? "!" : stepNum}
						</span>
						{step.label}
						{isViewOnlyReview && (
							<span
								className="text-[9px] ml-0.5"
								style={{ color: "var(--text-tertiary)" }}
							>
								(仅查看)
							</span>
						)}
					</button>
				);
			})}
			<div className="mt-4 pt-3 border-t border-gray-200">
				<button
					className="w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 rounded-md mb-1 transition-colors"
					onClick={onPause}
				>
					{"⏸"} 暂停
				</button>
				<button
					className="w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 rounded-md mb-1 transition-colors"
					onClick={onRetry}
				>
					{"↻"} 重试当前
				</button>
				<button
					className="w-full text-left px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 rounded-md transition-colors"
					onClick={onViewLogs}
				>
					{"📋"} 查看日志
				</button>
			</div>
		</div>
	);
}
