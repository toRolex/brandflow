import { useCallback, useEffect, useState } from "react";
import { DEFAULT_PAGE_SIZE } from "../api/core";
import {
	batchDeleteLogDates,
	cleanupLogs,
	deleteLogDate,
	downloadLogUrl,
	type LogDateInfo,
	listLogDates,
} from "../api/logs";
import ConfirmDialog from "../components/ConfirmDialog";
import InlineBanner from "../components/InlineBanner";
import Pagination from "../components/Pagination";

function formatSize(bytes: number): string {
	return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

/** Return today's date as YYYY-MM-DD in local timezone. */
function todayStr(): string {
	const d = new Date();
	const yyyy = d.getFullYear();
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	return `${yyyy}-${mm}-${dd}`;
}

type DeleteTarget =
	| { kind: "single"; date: string }
	| { kind: "batch"; dates: string[] }
	| { kind: "cleanup"; beforeDays: number };

export default function LogsPage() {
	const [logs, setLogs] = useState<LogDateInfo[]>([]);
	const [loading, setLoading] = useState(true);
	const [failed, setFailed] = useState(false);
	const [page, setPage] = useState(1);
	const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
	const [total, setTotal] = useState(0);
	const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set());
	const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
	const [cleanupDays, setCleanupDays] = useState(7);
	const [banner, setBanner] = useState<{
		type: "success" | "error";
		message: string;
	} | null>(null);

	const today = todayStr();

	const load = useCallback(() => {
		setLoading(true);
		setFailed(false);
		listLogDates(page, pageSize)
			.then((r) => {
				setLogs(r.items);
				setTotal(r.total);
			})
			.catch(() => setFailed(true))
			.finally(() => setLoading(false));
	}, [page, pageSize]);

	useEffect(() => {
		load();
	}, [load]);

	const handlePageChange = (p: number) => {
		setSelectedDates(new Set());
		setPage(p);
	};

	const handlePageSizeChange = (size: number) => {
		setSelectedDates(new Set());
		setPageSize(size);
		setPage(1);
	};

	/* ── selection ── */

	const allSelected = logs.length > 0 && selectedDates.size === logs.length;

	const toggleSelect = (date: string) => {
		setSelectedDates((prev) => {
			const next = new Set(prev);
			if (next.has(date)) next.delete(date);
			else next.add(date);
			return next;
		});
	};

	const toggleSelectAll = () => {
		if (allSelected) {
			setSelectedDates(new Set());
		} else {
			setSelectedDates(new Set(logs.map((l) => l.date)));
		}
	};

	/* ── delete confirmation ── */

	const startSingleDelete = (date: string) =>
		setDeleteTarget({ kind: "single", date });

	const startBatchDelete = () =>
		setDeleteTarget({ kind: "batch", dates: Array.from(selectedDates) });

	const startCleanup = () =>
		setDeleteTarget({ kind: "cleanup", beforeDays: cleanupDays });

	const confirmDelete = async () => {
		if (!deleteTarget) return;
		const target = deleteTarget;
		setDeleteTarget(null);

		let actualDeleted = 0;

		try {
			if (target.kind === "single") {
				const r = await deleteLogDate(target.date);
				actualDeleted = r.deleted ? 1 : 0;
				setBanner({
					type: "success",
					message: r.deleted
						? `已删除 ${target.date} 日志`
						: `日志文件 ${target.date} 不存在`,
				});
			} else if (target.kind === "batch") {
				const r = await batchDeleteLogDates(target.dates);
				actualDeleted = r.deleted.length;
				const parts: string[] = [];
				if (r.deleted.length) parts.push(`${r.deleted.length} 成功`);
				if (r.not_found.length) parts.push(`${r.not_found.length} 不存在`);
				if (r.protected.length) parts.push(`${r.protected.length} 受保护`);
				setBanner({
					type: r.deleted.length > 0 ? "success" : "error",
					message: parts.join("，") || "无操作",
				});
			} else {
				const r = await cleanupLogs(target.beforeDays);
				actualDeleted = r.deleted_count;
				setBanner({
					type: "success",
					message: `已清理 ${r.deleted_count} 个日志文件`,
				});
			}
		} catch (err: unknown) {
			const msg = err instanceof Error ? err.message : "操作失败";
			setBanner({ type: "error", message: msg });
		}

		setSelectedDates(new Set());
		// After deletion, check if we need to go back a page.
		// Use the *actual* number of deleted entries from the API response,
		// not the requested count — protected/not_found/failed entries
		// don't reduce the total.  Cleanup now participates too (was only a
		// reload before, leaving an empty last page visible).
		const remainingAfterDelete = total - actualDeleted;
		const maxPage = Math.max(1, Math.ceil(remainingAfterDelete / pageSize));
		if (page > maxPage) {
			setPage(maxPage);
		} else {
			load();
		}
	};

	/* ── delete confirm message ── */

	const getConfirmMessage = (): string => {
		if (!deleteTarget) return "";
		if (deleteTarget.kind === "single")
			return `确定要删除 ${deleteTarget.date} 的日志吗？此操作不可撤销。`;
		if (deleteTarget.kind === "batch")
			return `确定要删除选中的 ${deleteTarget.dates.length} 个日志文件吗？此操作不可撤销。`;
		return `确定要清理 ${deleteTarget.beforeDays} 天前的所有日志吗？此操作不可撤销。`;
	};

	/* ── render ── */

	if (loading)
		return (
			<p className="text-sm text-[var(--text-secondary)]">加载运行日志…</p>
		);
	if (failed)
		return (
			<p className="text-sm text-[var(--color-danger)]">加载运行日志失败</p>
		);

	return (
		<div className="space-y-4">
			{/* Header row */}
			<div className="flex items-center justify-between">
				<h1 className="text-lg font-semibold">运行日志</h1>

				{/* Cleanup control */}
				<div className="flex items-center gap-2 text-sm">
					<span style={{ color: "var(--text-secondary)" }}>清理</span>
					<input
						type="number"
						min={1}
						className="w-16 rounded border px-2 py-1 text-sm text-center"
						style={{
							background: "var(--input-bg)",
							color: "var(--input-text)",
							borderColor: "var(--input-border)",
						}}
						value={cleanupDays}
						onChange={(e) =>
							setCleanupDays(Math.max(1, Number(e.target.value)))
						}
					/>
					<span style={{ color: "var(--text-secondary)" }}>天前的日志</span>
					<button
						className="px-3 py-1 rounded text-xs font-medium transition-colors"
						style={{
							background: "var(--btn-danger-bg)",
							color: "var(--btn-danger-text)",
						}}
						onClick={startCleanup}
					>
						清理
					</button>
				</div>
			</div>

			{/* Banner */}
			{banner && (
				<InlineBanner
					type={banner.type}
					message={banner.message}
					onClose={() => setBanner(null)}
				/>
			)}

			{/* Bulk action bar */}
			{selectedDates.size > 0 && (
				<div
					className="flex items-center justify-between rounded-lg px-4 py-3 mb-4 border"
					style={{
						background: "var(--accent-bg, #eff6ff)",
						borderColor: "var(--border-default)",
					}}
				>
					<span
						className="text-sm font-semibold"
						style={{ color: "var(--text-primary)" }}
					>
						已选 {selectedDates.size} 天
					</span>
					<div className="flex gap-2">
						<button
							type="button"
							className="px-3 py-1.5 text-xs rounded-md font-medium transition-colors"
							style={{
								background: "var(--btn-danger-bg)",
								color: "var(--btn-danger-text)",
							}}
							onClick={startBatchDelete}
						>
							删除选中
						</button>
						<button
							type="button"
							className="px-3 py-1.5 text-xs rounded-md font-medium transition-colors"
							style={{
								background: "var(--btn-ghost-bg)",
								color: "var(--btn-ghost-text)",
								border: "1px solid var(--border-default)",
							}}
							onClick={() => setSelectedDates(new Set())}
						>
							取消选择
						</button>
					</div>
				</div>
			)}

			{logs.length === 0 ? (
				<p className="text-sm text-[var(--text-secondary)]">暂无运行日志</p>
			) : (
				<>
					<div className="border rounded-lg overflow-hidden border-[var(--border-default)]">
						<table className="w-full text-sm">
							<thead className="bg-[var(--bg-table-head)]">
								<tr>
									<th className="p-3 w-12">
										<input
											type="checkbox"
											aria-label="全选"
											checked={allSelected}
											onChange={toggleSelectAll}
										/>
									</th>
									<th className="p-3 text-left">日期</th>
									<th className="p-3 text-left">文件大小</th>
									<th className="p-3 text-left">错误条数</th>
									<th className="p-3 text-right">操作</th>
								</tr>
							</thead>
							<tbody>
								{logs.map((log) => {
									const isToday = log.date === today;
									return (
										<tr
											key={log.date}
											className="border-t border-[var(--border-default)]"
										>
											<td className="p-3">
												<input
													type="checkbox"
													aria-label={`选择 ${log.date}`}
													checked={selectedDates.has(log.date)}
													onChange={() => toggleSelect(log.date)}
												/>
											</td>
											<td className="p-3">{log.date}</td>
											<td className="p-3">{formatSize(log.size_bytes)}</td>
											<td className="p-3">{log.error_count}</td>
											<td className="p-3 text-right">
												<div className="flex gap-2 justify-end items-center">
													<a
														className="text-[var(--accent)] hover:underline"
														href={downloadLogUrl(log.date)}
														download={true}
													>
														下载
													</a>
													<button
														className="text-sm font-medium transition-colors"
														style={{
															color: isToday
																? "var(--text-tertiary)"
																: "var(--danger)",
															cursor: isToday ? "not-allowed" : "pointer",
															opacity: isToday ? 0.4 : 1,
														}}
														disabled={isToday}
														title={
															isToday ? "当天日志受保护，无法删除" : undefined
														}
														onClick={() => {
															if (!isToday) startSingleDelete(log.date);
														}}
													>
														删除
													</button>
												</div>
											</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					</div>

					<Pagination
						page={page}
						pageSize={pageSize}
						total={total}
						onPageChange={handlePageChange}
						onPageSizeChange={handlePageSizeChange}
					/>
				</>
			)}

			{/* Confirm dialog for all delete actions */}
			<ConfirmDialog
				isOpen={!!deleteTarget}
				title="确认删除"
				message={getConfirmMessage()}
				confirmLabel="确认删除"
				danger={true}
				onConfirm={confirmDelete}
				onCancel={() => setDeleteTarget(null)}
			/>
		</div>
	);
}
