import { useEffect, useState } from "react";

interface Props {
	text: string;
	onSave: (text: string) => void;
}

export default function SubtitleEditor({ text, onSave }: Props) {
	const [value, setValue] = useState(text);

	useEffect(() => {
		setValue(text);
	}, [text]);

	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">字幕文本</h3>
			<textarea
				className="w-full border rounded-lg p-3 text-sm font-mono min-h-[200px] resize-y"
				value={value}
				onChange={(e) => setValue(e.target.value)}
			/>
			<div className="flex gap-2 mt-2">
				<button
					className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] px-4 py-2 rounded-lg text-sm hover:bg-[var(--btn-primary-hover)] transition-colors"
					onClick={() => onSave(value)}
				>
					保存字幕
				</button>
				<button
					className="border px-4 py-2 rounded-lg text-sm hover:bg-[var(--bg-nav-active)] transition-colors"
					onClick={() => setValue(text)}
				>
					撤销
				</button>
			</div>
		</div>
	);
}
