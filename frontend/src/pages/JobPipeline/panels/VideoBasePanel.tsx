import MediaPlayer from "../../../components/MediaPlayer";
import type { PanelProps } from "../types";

export default function VideoBasePanel({ findArtifact }: PanelProps) {
	const video = findArtifact("video_base");
	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">底包拼接</h3>
			<MediaPlayer src={video?.url || ""} kind="video" />
		</div>
	);
}
