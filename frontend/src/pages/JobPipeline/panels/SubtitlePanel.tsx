import type { PanelProps } from "../types";

export default function SubtitlePanel({ findArtifact }: PanelProps) {
	const subtitleArtifact = findArtifact("subtitle");
	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">转录字幕</h3>
			{subtitleArtifact ? (
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
				<p className="text-[var(--text-tertiary)] text-sm">等待字幕生成...</p>
			)}
		</div>
	);
}
