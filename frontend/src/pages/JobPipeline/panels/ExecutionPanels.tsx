import type { Phase } from "../../../types";
import PhaseStatusNotice from "./PhaseStatusNotice";
import type { PanelProps } from "../types";

function ExecutionPanel({
	job,
	onRetry,
	getPhasePresentation,
	phase,
	title,
	completedMessage,
}: Pick<PanelProps, "job" | "onRetry" | "getPhasePresentation"> & {
	phase: Phase;
	title: string;
	completedMessage: string;
}) {
	const presentation = getPhasePresentation(phase);
	const canRetry =
		presentation.kind === "recoverable_error" && job.phase === "failed";

	return (
		<div>
			<h3 className="mb-3 text-sm font-semibold">{title}</h3>
			<PhaseStatusNotice presentation={presentation} />
			{presentation.kind === "completed" && (
				<p className="text-sm text-[var(--text-tertiary)]">{completedMessage}</p>
			)}
			{canRetry && (
				<button
					className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
					onClick={onRetry}
				>
					重试{title}
				</button>
			)}
		</div>
	);
}

export function MontagePanel(props: PanelProps) {
	return (
		<ExecutionPanel
			{...props}
			phase="montage_assembling"
			title="蒙太奇组装"
			completedMessage="蒙太奇组装完成，等待下一阶段。"
		/>
	);
}

export function FinalRenderPanel(props: PanelProps) {
	return (
		<ExecutionPanel
			{...props}
			phase="final_rendering"
			title="终审合成"
			completedMessage="最终视频已生成，等待终审。"
		/>
	);
}
