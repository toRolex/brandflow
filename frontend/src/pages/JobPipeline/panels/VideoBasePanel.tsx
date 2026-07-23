import MediaPlayer from "../../../components/MediaPlayer";
import PhaseStatusNotice from "./PhaseStatusNotice";
import type { PanelProps } from "../types";

export default function VideoBasePanel({ findArtifact, getPhasePresentation }: PanelProps) {
	const video = findArtifact("video_base");
	const presentation = getPhasePresentation("video_rendering");
	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">底包拼接</h3>
			{presentation.kind === "integrity_error" ? (
				<PhaseStatusNotice presentation={presentation} />
			) : video ? (
				<MediaPlayer src={video.url} kind="video" />
			) : (
				<PhaseStatusNotice presentation={presentation} />
			)}
		</div>
	);
}
