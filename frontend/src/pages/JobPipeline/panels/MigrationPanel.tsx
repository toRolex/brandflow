import { PanelProps } from "../types";

export default function MigrationPanel({
	sceneFolders,
	selectedSceneFolders,
	onSceneFolderToggle,
	onMigrateScenes,
}: PanelProps) {
	return (
		<div className="py-4">
			<div
				className="flex items-center gap-2 mb-4 p-3 rounded-lg border"
				style={{
					borderColor: "var(--color-caution-amber)",
					background: "var(--bg-table-head)",
				}}
			>
				<span
					className="text-lg shrink-0"
					style={{ color: "var(--color-caution-amber)" }}
				>
					&#9888;
				</span>
				<div>
					<h3
						className="font-semibold text-sm"
						style={{ color: "var(--text-primary)" }}
					>
						需补充场景文件夹
					</h3>
					<p
						className="text-xs mt-0.5"
						style={{ color: "var(--text-secondary)" }}
					>
						该任务为历史创建的导入任务，缺少有效的场景输入。请从下方选择场景文件夹完成迁移，系统将重建任务并保留现有文案与配置。
					</p>
				</div>
			</div>
			<p
				className="text-xs mb-4 font-medium"
				style={{ color: "var(--text-secondary)" }}
			>
				选择要使用的场景文件夹：
			</p>
			{sceneFolders.length === 0 ? (
				<p className="text-xs" style={{ color: "var(--text-secondary)" }}>
					未配置场景文件夹 — 请先在系统设置中配置场景文件夹
				</p>
			) : (
				<div className="flex flex-wrap gap-3 mb-4">
					{sceneFolders.map((folder) => (
						<label
							key={folder.path}
							className="flex items-center gap-1.5 text-sm cursor-pointer"
							style={{ color: "var(--text-primary)" }}
						>
							<input
								type="checkbox"
								checked={selectedSceneFolders.includes(folder.path)}
								onChange={(e) =>
									onSceneFolderToggle(folder.path, e.target.checked)
								}
							/>
							{folder.name}
						</label>
					))}
				</div>
			)}
			<button
				className="px-4 py-2 rounded-md text-sm disabled:opacity-50"
				style={{
					background: "var(--btn-primary-bg)",
					color: "var(--btn-primary-text)",
				}}
				disabled={selectedSceneFolders.length === 0}
				onClick={onMigrateScenes}
			>
				补充场景并重新启动任务
			</button>
		</div>
	);
}
