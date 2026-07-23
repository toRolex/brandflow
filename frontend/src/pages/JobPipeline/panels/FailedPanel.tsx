import { useNavigate } from "react-router-dom";
import { computePhasePresentation } from "../../../policies/phasePresentation";
import type { PanelProps } from "../types";

export default function FailedPanel({ job, onRetry }: PanelProps) {
	const navigate = useNavigate();
	const presentation = computePhasePresentation({
		phase: job.failed_phase ?? job.phase,
		execution: job.execution,
	});
	const isRetryable = presentation.showRetry;

	return (
		<div className="text-center py-12">
			<div className="text-[var(--color-alert-red)] text-5xl mb-4">{"✗"}</div>
			<h3 className="text-lg font-semibold text-[var(--color-alert-red)] mb-2">
				{presentation.title}
			</h3>
			<div className="space-y-2 text-sm text-[var(--text-tertiary)]">
				{presentation.errorCode && (
					<p className="font-mono text-[var(--color-alert-red)]">
						{presentation.errorCode}
					</p>
				)}
				{presentation.errorMessage && <p>{presentation.errorMessage}</p>}
				<p>{presentation.message}</p>
				{presentation.retryAttempt !== undefined &&
					presentation.maxRetryAttempts !== undefined && (
						<p>
							尝试次数：{presentation.retryAttempt} /{" "}
							{presentation.maxRetryAttempts}
						</p>
					)}
				{!isRetryable && (
					<p className="text-[var(--color-caution-amber)]">
						此错误不可重试，请检查配置后重建任务
					</p>
				)}
			</div>
			{isRetryable && (
				<button
					className="mt-4 bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
					onClick={onRetry}
				>
					重试失败阶段
				</button>
			)}
			{!isRetryable && (
				<button
					className="mt-4 bg-[var(--bg-table-head)] text-[var(--text-link)] border border-[var(--border-default)] px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
					onClick={() => navigate(`/projects/${job.project_id}`)}
				>
					返回工作台
				</button>
			)}
		</div>
	);
}
