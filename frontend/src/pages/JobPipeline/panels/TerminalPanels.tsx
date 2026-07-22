export function CancelledPanel() {
	return (
		<div className="text-center py-12">
			<div className="text-[var(--text-tertiary)] text-5xl mb-4">{"⊘"}</div>
			<h3 className="text-lg font-semibold text-[var(--text-tertiary)] mb-2">
				已取消
			</h3>
			<p className="text-[var(--text-tertiary)] text-sm">该任务已被人工取消</p>
		</div>
	);
}

export function PausedPanel() {
	return (
		<div className="text-center py-12">
			<div className="text-[var(--text-tag-yellow)] text-5xl mb-4">{"⏸"}</div>
			<h3 className="text-lg font-semibold text-[var(--text-tag-yellow)] mb-2">
				已暂停
			</h3>
			<p className="text-[var(--text-tertiary)] text-sm">
				任务已暂停，可点击“继续”恢复到暂停前的阶段
			</p>
		</div>
	);
}
