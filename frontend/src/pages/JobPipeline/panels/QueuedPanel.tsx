export default function QueuedPanel({ draft = false }: { draft?: boolean }) {
	return (
		<div className="text-[var(--text-tertiary)] text-sm py-4">
			{draft
				? "这是草稿，补全所需输入并入队后才会开始生产。"
				: "待调度：当前阶段尚未开始。"}
		</div>
	);
}
