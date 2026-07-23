import type { PanelProps } from "../types";
import PhaseStatusNotice from "./PhaseStatusNotice";

export default function SceneAssemblyPanel({
	job,
	onRetry,
	getPhasePresentation,
}: PanelProps) {
	const presentation = getPhasePresentation("scene_assembling");
	const canRetry =
		presentation.kind === "recoverable_error" && job.phase === "failed";

	return (
		<div>
			<h3 className="mb-3 text-sm font-semibold">场景拼接</h3>
			<PhaseStatusNotice presentation={presentation} />
			{presentation.kind === "completed" && (
				<p className="text-sm text-[var(--text-tertiary)]">
					场景拼接完成，等待下一阶段。
				</p>
			)}
			{canRetry && (
				<button
					className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
					onClick={onRetry}
				>
					重试场景拼接
				</button>
			)}
		</div>
	);
}
