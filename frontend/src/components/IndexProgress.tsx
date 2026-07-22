import VisionLogs from "./VisionLogs";

interface Props {
	step: string;
	progress: number;
	current: number;
	total: number;
	skippedCount: number;
	taskId?: string | null;
	isRunning?: boolean;
}

export default function IndexProgress({
	step,
	progress,
	current,
	total,
	skippedCount,
	taskId = null,
	isRunning = false,
}: Props) {
	const Steps = [
		{ key: "cut", label: "场景切分" },
		{ key: "frame", label: "关键帧提取" },
		{ key: "classify", label: "AI 分类" },
		{ key: "done", label: "入库完成" },
	];
	const stepOrder = ["cut", "frame", "classify", "done"];
	const currentIdx = stepOrder.indexOf(step);
	return (
		<div className="mb-4 p-3 bg-gray-50 border rounded-lg">
			<div className="flex items-center gap-2 mb-2">
				<div className="w-4 h-4 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin" />
				<span className="text-sm font-medium">正在处理视频</span>
				<span className="text-xs text-gray-400">
					({current}/{total})
				</span>
			</div>
			<div className="bg-gray-200 rounded-full h-2 mb-2 overflow-hidden">
				<div
					className="bg-blue-600 h-2 rounded-full transition-all"
					style={{
						width: `${progress}%`,
						transitionDuration: "var(--transition-duration-slow)",
					}}
				/>
			</div>
			<div className="text-xs text-gray-500 space-y-0.5">
				{Steps.map((s) => {
					const idx = stepOrder.indexOf(s.key);
					const done = idx <= currentIdx || step === "done";
					return (
						<div
							key={s.key}
							className={done ? "text-green-600" : "text-gray-400"}
						>
							{done ? "✓" : "○"} {s.label}
						</div>
					);
				})}
			</div>
			{skippedCount > 0 && (
				<div className="mt-2 pt-2 border-t border-gray-200 text-[11px] text-gray-400">
					已有 {skippedCount} 个切片不受影响，仅处理新视频
				</div>
			)}
			<VisionLogs taskId={taskId} isRunning={isRunning} />
		</div>
	);
}
