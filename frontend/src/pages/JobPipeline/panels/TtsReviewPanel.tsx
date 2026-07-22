import MediaPlayer from "../../../components/MediaPlayer";
import TtsVoiceSelector from "../components/TtsVoiceSelector";
import type { PanelProps } from "../types";

export default function TtsReviewPanel({
	isCurrentReviewStep,
	onApprove,
	onReject,
	...props
}: PanelProps) {
	const audio = props.findArtifact("tts_audio");
	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">TTS 审核</h3>
			<p className="text-[var(--text-tertiary)] text-sm mb-4">
				请试听TTS配音效果，确认无误后通过
			</p>
			<TtsVoiceSelector {...props} />
			<MediaPlayer src={audio?.url || props.ttsPreviewUrl || ""} kind="audio" />
			{!isCurrentReviewStep && (
				<div
					className="text-xs mb-2"
					style={{ color: "var(--color-caution-amber)" }}
				>
					当前不在该审核阶段，无法操作
				</div>
			)}
			<div className="flex gap-2 mt-4">
				<button
					className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
					onClick={() => onApprove("tts_review")}
					disabled={!isCurrentReviewStep}
					aria-disabled={!isCurrentReviewStep}
				>
					{"✓"} 通过
				</button>
				<button
					className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
					onClick={() => onReject("tts_review")}
					disabled={!isCurrentReviewStep}
					aria-disabled={!isCurrentReviewStep}
				>
					{"✗"} 打回重新生成
				</button>
			</div>
		</div>
	);
}
