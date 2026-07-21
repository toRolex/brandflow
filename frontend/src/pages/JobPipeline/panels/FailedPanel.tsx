import { useNavigate } from "react-router-dom";
import { PIPELINE_STEPS } from "../../../types";
import { PanelProps } from "../types";

export default function FailedPanel({ job, onRetry }: PanelProps) {
	const navigate = useNavigate();
	const executionError = job.execution?.error;
	const failedPhaseLabel = (() => {
		const step = PIPELINE_STEPS.find((s) => s.phase === job.failed_phase);
		return step?.label || "未知阶段";
	})();
	const isRetryable = executionError?.retryable === true;
	const isAssetFailed =
		job.failed_phase === "asset_retrieving" ||
		job.failed_phase === "asset_review";

	return (
		<div className="text-center py-12">
			<div className="text-[var(--color-alert-red)] text-5xl mb-4">{"✗"}</div>
			<h3 className="text-lg font-semibold text-[var(--color-alert-red)] mb-2">
				{isAssetFailed
					? isRetryable
						? "素材检索失败（可重试）"
						: "素材检索失败（已终止）"
					: "任务失败"}
			</h3>
			{executionError ? (
				<div className="space-y-2 text-sm text-[var(--text-tertiary)]">
					<p className="font-mono text-[var(--color-alert-red)]">
						{executionError.code}
					</p>
					<p>{executionError.message}</p>
					<p>
						失败阶段：
						<span className="font-mono">{failedPhaseLabel}</span>
					</p>
					{isRetryable ? (
						<p>
							尝试次数：{job.execution.current_attempt} /{" "}
							{job.execution.max_attempts}
						</p>
					) : (
						<p className="text-[var(--color-caution-amber)]">
							此错误不可重试，请检查配置后重建任务
						</p>
					)}
				</div>
			) : (
				<p className="text-[var(--text-tertiary)] text-sm">
					{job.last_error || "未知错误"}
				</p>
			)}
			{isRetryable && (
				<button
					className="mt-4 bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
					onClick={onRetry}
				>
					重试失败阶段
				</button>
			)}
			{!isRetryable && isAssetFailed && (
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
