import { PanelProps } from "../types";

function PhasePlaceholder({
	title,
	message,
}: {
	title?: string;
	message: string;
}) {
	return (
		<div className="py-4">
			{title && <h3 className="font-semibold text-sm mb-3">{title}</h3>}
			<p className="text-[var(--text-tertiary)] text-sm">{message}</p>
		</div>
	);
}

export function MontagePanel({ job, onRetry }: PanelProps) {
	const execStatus = job.execution?.status;
	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">蒙太奇组装</h3>
			{execStatus === "pending" && (
				<PhasePlaceholder title="蒙太奇" message="等待开始蒙太奇组装..." />
			)}
			{execStatus === "running" && (
				<div className="py-4">
					<div className="flex items-center gap-2 mb-2">
						<div
							className="w-4 h-4 border-2 rounded-full animate-spin"
							style={{
								borderColor: "var(--border-default)",
								borderTopColor: "var(--btn-primary-bg)",
							}}
						/>
						<p className="text-[var(--text-tertiary)] text-sm">
							正在组装蒙太奇...
						</p>
					</div>
				</div>
			)}
			{execStatus === "failed" && (
				<div className="py-4">
					<div
						className="p-3 rounded-lg border mb-3"
						style={{
							borderColor: "var(--alert-red)",
							background: "var(--alert-red-bg)",
						}}
					>
						<p className="text-sm font-medium text-[var(--alert-red)]">
							蒙太奇组装失败
						</p>
						{job.execution?.error && (
							<>
								<p className="text-xs mt-1 font-mono text-[var(--text-secondary)]">
									{job.execution.error.code}
								</p>
								<p className="text-xs mt-1 text-[var(--text-secondary)]">
									{job.execution.error.message}
								</p>
							</>
						)}
					</div>
					{job.execution?.error?.retryable && (
						<button
							className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
							onClick={onRetry}
						>
							重试蒙太奇组装
						</button>
					)}
				</div>
			)}
			{execStatus === "succeeded" && (
				<PhasePlaceholder
					title="蒙太奇"
					message="蒙太奇组装完成，等待下一阶段..."
				/>
			)}
			{!["pending", "running", "failed", "succeeded"].includes(
				execStatus || "",
			) && <PhasePlaceholder title="蒙太奇" message="等待系统调度..." />}
		</div>
	);
}

export function FinalRenderPanel({ job, onRetry }: PanelProps) {
	const execStatus = job.execution?.status;
	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">终审合成</h3>
			{execStatus === "pending" && (
				<PhasePlaceholder title="终审合成" message="等待开始终审合成..." />
			)}
			{execStatus === "running" && (
				<div className="py-4">
					<div className="flex items-center gap-2 mb-2">
						<div
							className="w-4 h-4 border-2 rounded-full animate-spin"
							style={{
								borderColor: "var(--border-default)",
								borderTopColor: "var(--btn-primary-bg)",
							}}
						/>
						<p className="text-[var(--text-tertiary)] text-sm">
							正在合成最终视频...
						</p>
					</div>
				</div>
			)}
			{execStatus === "failed" && (
				<div className="py-4">
					<div
						className="p-3 rounded-lg border mb-3"
						style={{
							borderColor: "var(--alert-red)",
							background: "var(--alert-red-bg)",
						}}
					>
						<p className="text-sm font-medium text-[var(--alert-red)]">
							终审合成失败
						</p>
						{job.execution?.error && (
							<>
								<p className="text-xs mt-1 font-mono text-[var(--text-secondary)]">
									{job.execution.error.code}
								</p>
								<p className="text-xs mt-1 text-[var(--text-secondary)]">
									{job.execution.error.message}
								</p>
							</>
						)}
					</div>
					{job.execution?.error?.retryable && (
						<button
							className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
							onClick={onRetry}
						>
							重试最终合成
						</button>
					)}
				</div>
			)}
			{execStatus === "succeeded" && (
				<PhasePlaceholder
					title="终审合成"
					message="终审合成完成，等待下一阶段..."
				/>
			)}
			{!["pending", "running", "failed", "succeeded"].includes(
				execStatus || "",
			) && <PhasePlaceholder title="终审合成" message="等待系统调度..." />}
		</div>
	);
}
