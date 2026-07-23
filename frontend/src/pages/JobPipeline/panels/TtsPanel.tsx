import MediaPlayer from "../../../components/MediaPlayer";
import TtsVoiceSelector from "../components/TtsVoiceSelector";
import type { PanelProps } from "../types";
import PhaseStatusNotice from "./PhaseStatusNotice";

export default function TtsPanel(props: PanelProps) {
	const { job, ttsPreviewUrl, onRetry, findArtifact, getPhasePresentation } =
		props;
	const audio = findArtifact("tts_audio");
	const presentation = getPhasePresentation("tts_generating", {
		requiredArtifacts: ["tts_audio"],
	});
	const canRetry =
		presentation.kind === "recoverable_error" && job.phase === "failed";

	return (
		<div>
			<h3 className="mb-3 text-sm font-semibold">TTS 配音</h3>
			<TtsVoiceSelector {...props} />
			<PhaseStatusNotice presentation={presentation} />
			{presentation.kind === "completed" && audio && (
				<MediaPlayer src={audio.url || ttsPreviewUrl} kind="audio" />
			)}
			{canRetry && (
				<button
					className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
					onClick={onRetry}
				>
					重试 TTS
				</button>
			)}
		</div>
	);
}
