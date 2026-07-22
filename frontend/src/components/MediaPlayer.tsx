import { useState } from "react";

interface Props {
	src: string;
	kind: "video" | "audio";
}

export default function MediaPlayer({ src, kind }: Props) {
	const [loadError, setLoadError] = useState(false);

	if (!src) {
		return <div className="text-gray-400 text-sm py-4">无媒体文件</div>;
	}

	if (loadError) {
		return (
			<div className="border border-dashed border-[var(--border-default)] rounded-lg p-8 text-center">
				<div className="text-3xl mb-2">🎬</div>
				<p className="text-gray-400 text-sm">视频文件加载失败</p>
			</div>
		);
	}

	if (kind === "video") {
		return (
			<video
				controls={true}
				className="w-full rounded-lg max-h-96"
				onError={() => setLoadError(true)}
			>
				<source src={src} />
				您的浏览器不支持视频播放
			</video>
		);
	}
	return (
		<audio
			controls={true}
			className="w-full"
			onError={() => setLoadError(true)}
		>
			<source src={src} />
			您的浏览器不支持音频播放
		</audio>
	);
}
