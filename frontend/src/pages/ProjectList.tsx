import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import BatchActionBar from "../components/BatchActionBar";
import ConfirmDialog from "../components/ConfirmDialog";
import InlineBanner from "../components/InlineBanner";
import type { Project } from "../types";

const BULK_DELETE_CONCURRENCY = 5;

async function runWithConcurrency<T, R>(
	items: T[],
	limit: number,
	fn: (item: T) => Promise<R>,
): Promise<PromiseSettledResult<R>[]> {
	const results: PromiseSettledResult<R>[] = new Array(items.length);
	const iterator = items.entries();

	async function worker(): Promise<void> {
		for (const [index, item] of iterator) {
			try {
				const value = await fn(item);
				results[index] = { status: "fulfilled", value };
			} catch (reason: unknown) {
				results[index] = { status: "rejected", reason };
			}
		}
	}

	await Promise.all(Array.from({ length: limit }, () => worker()));
	return results;
}

export default function ProjectList() {
	const [projects, setProjects] = useState<Project[]>([]);
	const [loading, setLoading] = useState(true);
	const [newName, setNewName] = useState("");
	const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
	const [bulkDeleteTargetIds, setBulkDeleteTargetIds] = useState<string[] | null>(
		null,
	);
	const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
	const [banner, setBanner] = useState<{
		type: "success" | "error";
		message: string;
	} | null>(null);
	const [highlightId, setHighlightId] = useState<string | null>(null);
	const inputRef = useRef<HTMLInputElement>(null);
	const headerCheckboxRef = useRef<HTMLInputElement>(null);
	const navigate = useNavigate();

	const load = useCallback(() => {
		setLoading(true);
		api
			.listProjects()
			.then(setProjects)
			.catch(() => {
				setProjects([]);
				setBanner({ type: "error", message: "加载项目列表失败" });
			})
			.finally(() => setLoading(false));
	}, []);

	useEffect(() => {
		load();
	}, [load]);

	const create = async () => {
		const name = newName.trim();
		if (!name) {
			setBanner({ type: "error", message: "项目名称不能为空" });
			return;
		}
		if (projects.some((p) => p.name === name)) {
			setBanner({ type: "error", message: "项目名称已存在，请使用其他名称" });
			return;
		}
		try {
			const p = await api.createProject(name);
			setNewName("");
			setHighlightId(p.id);
			setBanner({ type: "success", message: `项目「${p.name}」创建成功` });
			setTimeout(() => setHighlightId(null), 3000);
			await load();
		} catch (err: unknown) {
			const msg = err instanceof Error ? err.message : "创建失败，请重试";
			setBanner({ type: "error", message: msg });
		}
	};

	const focusInput = () => {
		inputRef.current?.focus();
	};

	const handleDelete = async (ids: string[]) => {
		const results = await runWithConcurrency(ids, BULK_DELETE_CONCURRENCY, (id) => {
			return api.deleteProject(id);
		});
		let successCount = 0;
		let failureCount = 0;
		for (const result of results) {
			if (result.status === "fulfilled") {
				successCount++;
			} else {
				failureCount++;
			}
		}

		setSelectedIds((prev) => {
			const next = new Set(prev);
			for (const id of ids) {
				next.delete(id);
			}
			return next;
		});
		setDeleteTarget(null);
		setBulkDeleteTargetIds(null);
		await load();

		if (failureCount === 0) {
			const text = successCount > 1 ? `已删除 ${successCount} 个项目` : "项目已删除";
			setBanner({ type: "success", message: text });
		} else {
			setBanner({
				type: "error",
				message: `${successCount} 成功，${failureCount} 失败`,
			});
		}
	};

	const confirmSingleDelete = () => {
		if (!deleteTarget) return;
		void handleDelete([deleteTarget.id]);
	};

	const confirmBulkDelete = () => {
		if (!bulkDeleteTargetIds?.length) return;
		void handleDelete(bulkDeleteTargetIds);
	};

	const allSelected = projects.length > 0 && selectedIds.size === projects.length;
	const someSelected = selectedIds.size > 0 && !allSelected;

	useEffect(() => {
		const el = headerCheckboxRef.current;
		if (el) {
			el.indeterminate = someSelected;
		}
	}, [someSelected]);

	const toggleSelect = (id: string) => {
		setSelectedIds((prev) => {
			const next = new Set(prev);
			if (next.has(id)) {
				next.delete(id);
			} else {
				next.add(id);
			}
			return next;
		});
	};

	const toggleSelectAll = () => {
		if (allSelected) {
			setSelectedIds(new Set());
		} else {
			setSelectedIds(new Set(projects.map((p) => p.id)));
		}
	};

	const clearSelection = () => setSelectedIds(new Set());

	return (
		<div>
			<div className="flex items-center justify-between mb-6">
				<h1
					className="text-xl font-bold"
					style={{ color: "var(--text-primary)" }}
				>
					项目列表
				</h1>
				<div className="flex gap-2">
					<input
						ref={inputRef}
						className="rounded-lg px-3 py-2 text-sm w-48 border"
						style={{
							background: "var(--input-bg)",
							color: "var(--input-text)",
							borderColor: "var(--input-border)",
						}}
						placeholder="新项目名称"
						value={newName}
						onChange={(e) => setNewName(e.target.value)}
						onKeyDown={(e) => e.key === "Enter" && create()}
					/>
					<button
						className="text-white px-4 py-2 rounded-lg text-sm font-semibold transition-all"
						style={{
							background: "var(--btn-primary-bg)",
							color: "var(--btn-primary-text)",
						}}
						onClick={create}
						onMouseEnter={(e) => {
							e.currentTarget.style.background = "var(--btn-primary-hover)";
						}}
						onMouseLeave={(e) => {
							e.currentTarget.style.background = "var(--btn-primary-bg)";
						}}
					>
						创建项目
					</button>
				</div>
			</div>

			{banner && (
				<InlineBanner
					type={banner.type}
					message={banner.message}
					onClose={() => setBanner(null)}
				/>
			)}

			{selectedIds.size > 0 && (
				<BatchActionBar
					count={selectedIds.size}
					label={(count) => `已选 ${count} 项`}
					onDelete={() => setBulkDeleteTargetIds([...selectedIds])}
					onClear={clearSelection}
				/>
			)}

			{loading ? (
				<div className="text-center py-16">
					<p className="text-sm" style={{ color: "var(--text-tertiary)" }}>
						加载中...
					</p>
				</div>
			) : projects.length === 0 ? (
				<div className="text-center py-16">
					<p
						className="text-lg font-semibold mb-2"
						style={{ color: "var(--text-primary)" }}
					>
						开始你的第一个项目
					</p>
					<p
						className="text-sm mb-6"
						style={{ color: "var(--text-tertiary)" }}
					>
						创建项目后，即可批量生产短视频内容
					</p>
					<button
						className="text-white px-5 py-2.5 rounded-lg text-sm font-semibold transition-all"
						style={{
							background: "var(--btn-primary-bg)",
							color: "var(--btn-primary-text)",
						}}
						onClick={focusInput}
						onMouseEnter={(e) => {
							e.currentTarget.style.background = "var(--btn-primary-hover)";
						}}
						onMouseLeave={(e) => {
							e.currentTarget.style.background = "var(--btn-primary-bg)";
						}}
					>
						新建项目
					</button>
				</div>
			) : (
				<div
					className="rounded-xl overflow-hidden border"
					style={{ borderColor: "var(--border-default)" }}
				>
					<table className="w-full border-collapse text-sm">
						<thead>
							<tr
								className="border-b text-left"
								style={{
									background: "var(--bg-table-head)",
									borderColor: "var(--border-default)",
									color: "var(--text-secondary)",
								}}
							>
								<th className="py-3 px-4 font-medium w-12">
									<input
										ref={headerCheckboxRef}
										type="checkbox"
										aria-label="全选"
										checked={allSelected}
										onChange={toggleSelectAll}
									/>
								</th>
								<th className="py-3 px-4 font-medium">项目名称</th>
								<th className="py-3 px-4 font-medium">状态</th>
								<th className="py-3 px-4 font-medium">Jobs</th>
								<th className="py-3 px-4 font-medium">操作</th>
							</tr>
						</thead>
						<tbody>
							{projects.map((p) => (
								<tr
									key={p.id}
									className="border-b transition-colors"
									style={{
										borderColor: "var(--border-default)",
										background:
											p.id === highlightId
												? "var(--success-bg)"
												: undefined,
									}}
									onMouseEnter={(e) => {
										e.currentTarget.style.background = "var(--bg-nav-active)";
									}}
									onMouseLeave={(e) => {
										e.currentTarget.style.background =
											p.id === highlightId
												? "var(--success-bg)"
												: "";
									}}
								>
									<td className="py-3 px-4">
										<input
											type="checkbox"
											aria-label={`选择项目 ${p.name || p.id}`}
											checked={selectedIds.has(p.id)}
											onChange={() => toggleSelect(p.id)}
										/>
									</td>
									<td
										className="py-3 px-4 font-medium"
										style={{ color: "var(--text-primary)" }}
									>
										{p.name || p.id}
									</td>
									<td
										className="py-3 px-4"
										style={{ color: "var(--text-secondary)" }}
									>
										{p.status}
									</td>
									<td
										className="py-3 px-4"
										style={{ color: "var(--text-secondary)" }}
									>
										{p.job_count}
									</td>
									<td className="py-3 px-4">
										<div className="flex gap-2">
											<button
												className="text-sm font-medium transition-colors"
												style={{ color: "var(--text-link)" }}
												onClick={() => navigate(`/projects/${p.id}`)}
												onMouseEnter={(e) => {
													e.currentTarget.style.opacity = "0.8";
												}}
												onMouseLeave={(e) => {
													e.currentTarget.style.opacity = "";
												}}
											>
												打开 →
											</button>
											<button
												className="text-sm font-medium transition-colors"
												style={{ color: "var(--danger)" }}
												onClick={() => setDeleteTarget(p)}
												onMouseEnter={(e) => {
													e.currentTarget.style.opacity = "0.8";
												}}
												onMouseLeave={(e) => {
													e.currentTarget.style.opacity = "";
												}}
											>
												删除
											</button>
										</div>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}

			<ConfirmDialog
				isOpen={!!deleteTarget}
				title="确认删除"
				message={`确定要删除项目「${deleteTarget?.name || deleteTarget?.id || ""}」吗？此操作不可撤销。`}
				confirmLabel="确认删除"
				danger
				onConfirm={confirmSingleDelete}
				onCancel={() => setDeleteTarget(null)}
			/>

			<ConfirmDialog
				isOpen={!!bulkDeleteTargetIds}
				title="确认批量删除"
				message={`确定要删除已选中的 ${bulkDeleteTargetIds?.length ?? 0} 个项目吗？此操作不可撤销。`}
				confirmLabel="确认删除"
				danger
				onConfirm={confirmBulkDelete}
				onCancel={() => setBulkDeleteTargetIds(null)}
			/>
		</div>
	);
}
