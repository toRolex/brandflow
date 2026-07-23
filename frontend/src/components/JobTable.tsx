import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { JobSummary } from "../types";
import StatusBadge from "./StatusBadge";

interface Props {
	jobs: JobSummary[];
	onRetry: (jobId: string) => void;
	onDelete: (jobId: string) => void;
	onRename?: (jobId: string, name: string) => Promise<void>;
	/** 当前选中的 job ID 集合，传入即启用多选模式 */
	selectedJobIds?: Set<string>;
	/** 选中变化回调 */
	onSelectionChange?: (ids: Set<string>) => void;
}

export default function JobTable({
	jobs,
	onRetry,
	onDelete,
	onRename,
	selectedJobIds,
	onSelectionChange,
}: Props) {
	const navigate = useNavigate();
	const [exporting, setExporting] = useState(false);

	if (jobs.length === 0) {
		return (
			<p className="text-sm py-4" style={{ color: "var(--text-secondary)" }}>
				暂无 Job，创建一个开始吧
			</p>
		);
	}

	const showCheckbox = selectedJobIds !== undefined;

	const completedJobs = jobs.filter((j) => j.phase === "completed");
	const allCompletedSelected =
		completedJobs.length > 0 &&
		completedJobs.every((j) => selectedJobIds?.has(j.job_id));

	function toggleSelectAll() {
		if (!onSelectionChange || !selectedJobIds) return;
		const newSet = new Set(selectedJobIds);
		if (allCompletedSelected) {
			completedJobs.forEach((j) => newSet.delete(j.job_id));
		} else {
			completedJobs.forEach((j) => newSet.add(j.job_id));
		}
		onSelectionChange(newSet);
	}

	function toggleJob(jobId: string) {
		if (!onSelectionChange || !selectedJobIds) return;
		const newSet = new Set(selectedJobIds);
		if (newSet.has(jobId)) {
			newSet.delete(jobId);
		} else {
			newSet.add(jobId);
		}
		onSelectionChange(newSet);
	}

	const selectedCompletedCount = jobs.filter(
		(j) => selectedJobIds?.has(j.job_id) && j.phase === "completed",
	).length;

	async function handleExport() {
		if (!selectedJobIds || !onSelectionChange) return;
		setExporting(true);
		try {
			// File System Access API — 仅在 Chromium 系浏览器可用
			const dirHandle = await (window as any).showDirectoryPicker();
			const selected = jobs.filter(
				(j) => selectedJobIds.has(j.job_id) && j.phase === "completed",
			);
			for (const job of selected) {
				const ext = job;
				const finalVideo = ext.artifacts?.find((a) => a.kind === "final_video");
				if (!finalVideo?.url) continue;

				const response = await fetch(finalVideo.url);
				if (!response.ok) continue;
				const blob = await response.blob();

				const idx = ext.display_index ?? "_";
				const product = job.product || "unknown";
				const name = job.name || job.product || "untitled";
				const rawName = `${idx}_${product}_${name}.mp4`;
				const filename = rawName.replace(/[/\\?%*:|"<>]/g, "_");

				const fileHandle = await dirHandle.getFileHandle(filename, {
					create: true,
				});
				const writable = await fileHandle.createWritable();
				await writable.write(blob);
				await writable.close();
			}
		} finally {
			setExporting(false);
		}
	}

	return (
		<div>
			<table className="w-full border-collapse text-[13px]">
				<thead>
					<tr
						className="border-b text-left"
						style={{
							borderColor: "var(--border-default)",
							color: "var(--text-secondary)",
						}}
					>
						{showCheckbox && (
							<th className="py-2 px-2 font-medium w-8">
								<input
									type="checkbox"
									checked={allCompletedSelected}
									onChange={toggleSelectAll}
									style={{ accentColor: "var(--accent)" }}
								/>
							</th>
						)}
						<th className="py-2 px-2 font-medium w-12">序号</th>
						<th className="py-2 px-2 font-medium">Job ID</th>
						<th className="py-2 px-2 font-medium">名称</th>
						<th className="py-2 px-2 font-medium">产品</th>
						<th className="py-2 px-2 font-medium">状态</th>
						<th className="py-2 px-2 font-medium">进度</th>
						<th className="py-2 px-2 font-medium">操作</th>
					</tr>
				</thead>
				<tbody>
					{jobs.map((j) => {
						const ext = j;
						const isCompleted = j.phase === "completed";
						return (
							<NameRow
								key={j.job_id}
								job={j}
								onRename={onRename}
								onRetry={onRetry}
								onDelete={onDelete}
								navigate={navigate}
								showCheckbox={showCheckbox}
								isSelected={selectedJobIds?.has(j.job_id) ?? false}
								isCompleted={isCompleted}
								displayIndex={ext.display_index}
								onToggle={() => toggleJob(j.job_id)}
							/>
						);
					})}
				</tbody>
			</table>

			{showCheckbox && selectedJobIds!.size > 0 && (
				<div
					className="flex items-center justify-between mt-3 px-3 py-2 border rounded-md"
					style={{
						background: "var(--bg-page)",
						borderColor: "var(--border-default)",
					}}
				>
					<span className="text-sm" style={{ color: "var(--text-secondary)" }}>
						已选 {selectedCompletedCount} 个已完成 Job
					</span>
					<button
						className="px-3 py-1.5 text-xs rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
						style={{
							background: "var(--accent)",
							color: "var(--text-inverse)",
						}}
						disabled={exporting || selectedCompletedCount === 0}
						onClick={handleExport}
					>
						{exporting ? "导出中…" : "导出视频"}
					</button>
				</div>
			)}
		</div>
	);
}

function NameRow({
	job,
	onRename,
	onRetry,
	onDelete,
	navigate,
	showCheckbox,
	isSelected,
	isCompleted,
	displayIndex,
	onToggle,
}: {
	job: JobSummary;
	onRename?: (jobId: string, name: string) => Promise<void>;
	onRetry: (jobId: string) => void;
	onDelete: (jobId: string) => void;
	navigate: ReturnType<typeof useNavigate>;
	showCheckbox?: boolean;
	isSelected?: boolean;
	isCompleted?: boolean;
	displayIndex?: string;
	onToggle?: () => void;
}) {
	const [editing, setEditing] = useState(false);
	const [draft, setDraft] = useState(job.name || job.product);

	const displayName = job.name || job.product;

	const commit = async () => {
		const trimmed = draft.trim();
		if (trimmed && trimmed !== displayName && onRename) {
			await onRename(job.job_id, trimmed);
		}
		setEditing(false);
		setDraft(job.name || job.product);
	};

	return (
		<tr className="border-b" style={{ borderColor: "var(--border-default)" }}>
			{showCheckbox && (
				<td className="py-2.5 px-2">
					<input
						type="checkbox"
						checked={isSelected ?? false}
						onChange={onToggle}
						disabled={!isCompleted}
						style={{ accentColor: "var(--accent)" }}
						className="disabled:opacity-30"
					/>
				</td>
			)}
			<td
				className="py-2.5 px-2 font-mono text-xs"
				style={{ color: "var(--accent)" }}
			>
				{displayIndex == null ? "—" : displayIndex}
			</td>
			<td className="py-2.5 px-2 font-mono text-xs">{job.job_id}</td>
			<td className="py-2.5 px-2">
				{editing ? (
					<input
						type="text"
						className="border rounded px-1.5 py-0.5 text-xs w-32"
						value={draft}
						onChange={(e) => setDraft(e.target.value)}
						onBlur={commit}
						onKeyDown={(e) => {
							if (e.key === "Enter") commit();
							if (e.key === "Escape") {
								setEditing(false);
								setDraft(job.name || job.product);
							}
						}}
						autoFocus={true}
					/>
				) : (
					<span
						className="cursor-pointer"
						style={{ color: "var(--text-primary)" }}
						title="双击编辑名称"
						onDoubleClick={() => {
							setEditing(true);
							setDraft(job.name || job.product);
						}}
					>
						{displayName}
					</span>
				)}
			</td>
			<td className="py-2.5 px-2">{job.product}</td>
			<td className="py-2.5 px-2">
				<StatusBadge phase={job.phase} />
				{job.phase === "asset_review" &&
					job.asset_review_unresolved_count != null && (
						<div className="text-xs mt-1" style={{ color: "var(--color-caution-amber)" }}>
							待处理素材：{job.asset_review_unresolved_count} 条
						</div>
					)}
			</td>
			<td className="py-2.5 px-2" style={{ color: "var(--text-secondary)" }}>
				{job.phase_index > 0 ? `${job.phase_index}/${job.phase_total}` : "—"}
			</td>
			<td className="py-2.5 px-2 flex gap-2 items-center">
				{job.phase === "failed" ? (
					<button
						className="hover:underline text-xs"
						style={{ color: "var(--accent)" }}
						onClick={() => onRetry(job.job_id)}
					>
						重试 &#8634;
					</button>
				) : (
					<button
						className="hover:underline text-xs"
						style={{ color: "var(--accent)" }}
						onClick={() => navigate(`/jobs/${job.job_id}`)}
					>
						查看 &rarr;
					</button>
				)}
				{["draft", "paused", "failed", "cancelled", "completed"].includes(
					job.phase,
				) && (
					<button
						className="hover:underline text-xs"
						style={{ color: "var(--danger)" }}
						onClick={() => onDelete(job.job_id)}
					>
						删除
					</button>
				)}
			</td>
		</tr>
	);
}
