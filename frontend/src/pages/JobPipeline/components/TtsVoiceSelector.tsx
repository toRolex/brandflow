import { api } from "../../../api/client";
import type { PanelProps } from "../types";

type SelectorProps = Pick<
	PanelProps,
	| "job"
	| "ttsVoiceInfo"
	| "ttsSelectedModel"
	| "ttsSelectedVoice"
	| "ttsVoices"
	| "ttsPreviewUrl"
	| "ttsPreviewLoading"
	| "showVoiceConfirm"
	| "ttsVoiceError"
	| "onTtsModelChange"
	| "onTtsVoiceChange"
	| "onTtsPreview"
	| "onApplyVoiceChange"
	| "onConfirmVoiceChange"
	| "onCancelVoiceChange"
>;

export default function TtsVoiceSelector({
	job,
	ttsVoiceInfo,
	ttsSelectedModel,
	ttsSelectedVoice,
	ttsVoices,
	ttsPreviewUrl,
	ttsPreviewLoading,
	showVoiceConfirm,
	ttsVoiceError,
	onTtsModelChange,
	onTtsVoiceChange,
	onTtsPreview,
	onApplyVoiceChange,
	onConfirmVoiceChange,
	onCancelVoiceChange,
}: SelectorProps) {
	// Upload/library audio source: TTS controls not applicable (#252)
	if (job.audio_source === "upload" || job.audio_source === "library") {
		return (
			<div
				className="mb-4 p-3 rounded-lg border"
				style={{
					borderColor: "var(--border-default)",
					background: "var(--bg-table-head)",
				}}
			>
				<span className="text-xs" style={{ color: "var(--text-secondary)" }}>
					此 Job 使用已有音频，TTS 设置不生效
				</span>
			</div>
		);
	}

	const ResolvedLabels: Record<string, string> = {
		job: "Job 覆盖",
		product: "产品",
		global: "全局",
	};
	const resolvedLabel = ttsVoiceInfo
		? ResolvedLabels[ttsVoiceInfo.resolved_from] || ttsVoiceInfo.resolved_from
		: "";
	const resolvedBadgeColor =
		ttsVoiceInfo?.resolved_from === "job"
			? "var(--btn-primary-bg)"
			: ttsVoiceInfo?.resolved_from === "product"
				? "var(--color-caution-amber)"
				: "var(--text-tertiary)";

	return (
		<div
			className="mb-4 p-3 rounded-lg border"
			style={{
				borderColor: "var(--border-default)",
				background: "var(--bg-table-head)",
			}}
		>
			{ttsVoiceInfo && (
				<>
					<div className="flex items-center gap-2 mb-3">
						<span
							className="text-xs"
							style={{ color: "var(--text-secondary)" }}
						>
							当前音色:
						</span>
						<span
							className="text-xs font-mono"
							style={{ color: "var(--text-primary)" }}
						>
							{ttsVoiceInfo.model} / {ttsVoiceInfo.voice}
						</span>
						<span
							className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
							style={{ background: resolvedBadgeColor, color: "#fff" }}
						>
							{resolvedLabel}
						</span>
					</div>

					<div
						className="text-xs mb-2"
						style={{ color: "var(--text-secondary)" }}
					>
						所属产品：{ttsVoiceInfo.product}
					</div>
				</>
			)}

			<div className="flex flex-wrap items-center gap-2 mb-2">
				<select
					className="text-xs border rounded px-2 py-1"
					style={{
						borderColor: "var(--border-default)",
						background: "var(--bg-page)",
						color: "var(--text-primary)",
					}}
					value={ttsSelectedModel}
					onChange={(e) => {
						const newModel = e.target.value;
						onTtsModelChange(newModel);
						api
							.getTTSVoices(undefined, newModel)
							.then(
								(data: { preset_voices: { id: string }[] }) => {
									if (data.preset_voices.length > 0) {
										const isPresetModel =
											newModel === "mimo-v2.5-tts" ||
											newModel === "qwen3-tts-flash" ||
											newModel === "qwen3-tts-instruct-flash";
										if (isPresetModel) {
											onTtsVoiceChange(data.preset_voices[0].id);
										}
									}
								},
							)
							.catch(() => {});
					}}
				>
					{ttsVoiceInfo && (
						<option value={ttsVoiceInfo.model}>
							{ttsVoiceInfo.model} (当前)
						</option>
					)}
					<option value="mimo-v2.5-tts">mimo-v2.5-tts</option>
					<option value="mimo-v2.5-tts-voicedesign">
						mimo-v2.5-tts-voicedesign
					</option>
					<option value="mimo-v2.5-tts-voiceclone">
						mimo-v2.5-tts-voiceclone
					</option>
					<option value="qwen3-tts-flash">qwen3-tts-flash</option>
					<option value="qwen3-tts-instruct-flash">
						qwen3-tts-instruct-flash
					</option>
				</select>

				<select
					className="text-xs border rounded px-2 py-1 flex-1 min-w-[120px]"
					style={{
						borderColor: "var(--border-default)",
						background: "var(--bg-page)",
						color: "var(--text-primary)",
					}}
					value={ttsSelectedVoice}
					onChange={(e) => onTtsVoiceChange(e.target.value)}
				>
					{ttsVoices.length === 0 && ttsVoiceInfo && (
						<option value={ttsVoiceInfo.voice}>
							{ttsVoiceInfo.voice} (当前)
						</option>
					)}
					{ttsVoices.map((v) => (
						<option key={v.id} value={v.id}>
							{v.label} ({v.id})
						</option>
					))}
				</select>

				<button
					className="text-xs px-3 py-1 rounded-md"
					style={{
						background: "var(--btn-primary-bg)",
						color: "var(--btn-primary-text)",
					}}
					onClick={() =>
						onApplyVoiceChange(ttsSelectedModel, ttsSelectedVoice)
					}
				>
					应用
				</button>
			</div>

			{ttsVoiceError && (
				<div
					className="mt-2 text-xs px-3 py-2 rounded"
					style={{
						background: "var(--alert-red-muted)",
						color: "var(--alert-red)",
						border: "1px solid var(--danger-border)",
					}}
				>
					{ttsVoiceError}
				</div>
			)}

			<div className="flex items-center gap-2">
				<button
					className="text-xs px-3 py-1 rounded-md disabled:opacity-50"
					style={{
						background: "var(--bg-table-head)",
						color: "var(--text-link)",
						border: "1px solid var(--border-default)",
					}}
					onClick={onTtsPreview}
					disabled={ttsPreviewLoading}
				>
					{ttsPreviewLoading ? "试听中..." : "试听"}
				</button>
				{ttsPreviewUrl && (
					<span
						className="text-[10px]"
						style={{ color: "var(--signal-green)" }}
					>
						试听就绪
					</span>
				)}
			</div>

			<div className="mt-2">
				<a
					href="/tts-config"
					className="text-[10px] hover:underline"
					style={{ color: "var(--text-tertiary)" }}
					target="_blank"
					rel="noopener noreferrer"
				>
					高级 TTS 配置
				</a>
			</div>

			{showVoiceConfirm && (
				<div
					className="mt-3 p-3 rounded-lg border"
					style={{
						borderColor: "var(--danger-border)",
						background: "var(--alert-red-muted)",
					}}
				>
					<p className="text-xs mb-2" style={{ color: "var(--alert-red)" }}>
						正式 TTS
						音频已存在，更换音色将失效下游产物（字幕、视频等），确认继续？
					</p>
					<div className="flex gap-2">
						<button
							className="text-xs px-3 py-1 rounded-md"
							style={{
								background: "var(--btn-danger-bg)",
								color: "var(--btn-danger-text)",
							}}
							onClick={onConfirmVoiceChange}
						>
							确认更换
						</button>
						<button
							className="text-xs px-3 py-1 rounded-md"
							style={{
								background: "var(--bg-page)",
								color: "var(--text-primary)",
								border: "1px solid var(--border-default)",
							}}
							onClick={onCancelVoiceChange}
						>
							取消
						</button>
					</div>
				</div>
			)}
		</div>
	);
}
