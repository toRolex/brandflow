import MediaPlayer from "../../../components/MediaPlayer";
import TtsVoiceSelector from "../components/TtsVoiceSelector";
import type { PanelProps } from "../types";

export default function TtsPanel(props: PanelProps) {
	const { job, ttsPreviewUrl, onRetry, findArtifact } = props;
	const audio = findArtifact("tts_audio");
	const execStatus = job.execution?.status;
	const execError = job.execution?.error;

	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">TTS 配音</h3>
			<TtsVoiceSelector {...props} />

			{execStatus === "pending" && (
				<div className="py-4">
					<p className="text-[var(--text-tertiary)] text-sm">
						等待开始 TTS 合成...
					</p>
				</div>
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
							正在合成 TTS 音频...
						</p>
					</div>
					<p className="text-[var(--text-tertiary)] text-xs">
						第 {job.execution.current_attempt} / {job.execution.max_attempts}{" "}
						次重试
					</p>
				</div>
			)}

			{execStatus === "retrying" && execError && (
				<div className="mb-4">
					<div
						className="p-3 rounded-lg border mb-3"
						style={{
							borderColor: "var(--color-caution-amber)",
							background: "var(--bg-table-head)",
						}}
					>
						<div className="flex items-center gap-2 mb-1">
							<span
								className="text-sm font-medium"
								style={{ color: "var(--color-caution-amber)" }}
							>
								正在重试
							</span>
							<span
								className="text-xs"
								style={{ color: "var(--text-tertiary)" }}
							>
								第 {job.execution.current_attempt} /{" "}
								{job.execution.max_attempts} 次
							</span>
						</div>
						<p
							className="text-xs font-mono mt-1"
							style={{ color: "var(--color-caution-amber)" }}
						>
							{execError.code}
						</p>
						<p
							className="text-xs mt-1"
							style={{ color: "var(--text-secondary)" }}
						>
							{execError.message}
						</p>
					</div>
				</div>
			)}

			{(!execStatus ||
				execStatus === "succeeded" ||
				execStatus === "pending") && (
				<MediaPlayer src={audio?.url || ttsPreviewUrl || ""} kind="audio" />
			)}

			{execStatus === "failed" && execError && (
				<div className="mb-4">
					<div
						className="p-3 rounded-lg border mb-3"
						style={{
							borderColor: "var(--danger-border)",
							background: "var(--alert-red-muted)",
						}}
					>
						<p
							className="text-sm font-medium mb-1"
							style={{ color: "var(--alert-red)" }}
						>
							TTS 合成失败
						</p>
						<p
							className="text-xs font-mono mt-1"
							style={{ color: "var(--alert-red)" }}
						>
							{execError.code}
						</p>
						<p
							className="text-xs mt-1"
							style={{ color: "var(--text-secondary)" }}
						>
							{execError.message}
						</p>
						{!execError.retryable && (
							<p
								className="text-xs mt-1"
								style={{ color: "var(--color-caution-amber)" }}
							>
								此错误不可重试，请检查 TTS 配置或更换模型/音色
							</p>
						)}
					</div>
					{execError.retryable && (
						<button
							className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
							onClick={onRetry}
						>
							重试 TTS
						</button>
					)}
				</div>
			)}
		</div>
	);
}
