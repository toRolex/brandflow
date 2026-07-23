import type { PanelProps } from "../types";
import PhaseStatusNotice from "./PhaseStatusNotice";

export default function SubtitlePanel({ findArtifact, getPhasePresentation }: PanelProps) {
	const subtitleArtifact = findArtifact("subtitle");
	const presentation = getPhasePresentation("subtitle_generating");
	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">转录字幕</h3>
			{presentation.kind === "integrity_error" ? (
				<PhaseStatusNotice presentation={presentation} />
			) : subtitleArtifact ? (
				<div>
					<p className="text-[var(--text-tertiary)] text-sm mb-2">
						字幕文件已生成
					</p>
					<a
						href={subtitleArtifact.url}
						target="_blank"
						rel="noopener noreferrer"
						className="text-[var(--text-link)] hover:underline text-sm"
					>
						下载字幕文件 ({subtitleArtifact.kind})
					</a>
				</div>
			) : (
				<PhaseStatusNotice presentation={presentation} />
			)}
		</div>
	);
}
