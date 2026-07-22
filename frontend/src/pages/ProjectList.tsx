import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import ConfirmDialog from "../components/ConfirmDialog";
import InlineBanner from "../components/InlineBanner";
import Modal from "../components/Modal";
import type { Project } from "../types";
import ConfirmDialog from "../components/ConfirmDialog";
import InlineBanner from "../components/InlineBanner";
import Modal from "../components/Modal";

export default function ProjectList() {
	const [projects, setProjects] = useState<Project[]>([]);
	const [loading, setLoading] = useState(true);
	const [showCreateModal, setShowCreateModal] = useState(false);
	const [createName, setCreateName] = useState("");
	const [createError, setCreateError] = useState<string | null>(null);
	const [banner, setBanner] = useState<{
		type: "success" | "error";
		message: string;
	} | null>(null);
	const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
	const [showBulkDeleteModal, setShowBulkDeleteModal] = useState(false);
	const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
	const [highlightId, setHighlightId] = useState<string | null>(null);
	const createInputRef = useRef<HTMLInputElement>(null);
	const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const navigate = useNavigate();

	const load = useCallback(() => {
		setLoading(true);
		api
			.listProjects()
			.then(setProjects)
			.catch(() => setProjects([]))
			.finally(() => setLoading(false));
	}, []);

	useEffect(() => {
		load();
	}, [load]);

	useEffect(() => {
		if (showCreateModal) {
			setTimeout(() => createInputRef.current?.focus(), 50);
		}
	}, [showCreateModal]);

	// Clean up highlight timer on unmount
	useEffect(
		() => () => {
			if (highlightTimerRef.current) {
				clearTimeout(highlightTimerRef.current);
			}
		},
		[],
	);

	const validateName = (name: string): string | null => {
		if (!name.trim()) return "项目名称不能为空";
		if (projects.some((p) => p.name === name.trim()))
			return "项目名称已存在，请使用其他名称";
		return null;
	};

	const handleCreate = async () => {
		const name = createName.trim();
		const validationError = validateName(name);
		if (validationError) {
			setCreateError(validationError);
			return;
		}
		setCreateError(null);
		try {
			const p = await api.createProject(name);
			setCreateName("");
			setShowCreateModal(false);
			setCreateError(null);
			load();
			setHighlightId(p.id);
			setBanner({ type: "success", message: `项目「${p.name}」创建成功` });
			if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
			highlightTimerRef.current = setTimeout(() => setHighlightId(null), 3000);
		} catch (err: unknown) {
			const msg = err instanceof Error ? err.message : "创建失败，请重试";
			setBanner({ type: "error", message: msg });
			// Keep modal open so user can retry
		}
	};

	const confirmDelete = async () => {
		if (!deleteTarget) return;
		try {
			await api.deleteProject(deleteTarget.id);
			setDeleteTarget(null);
			load();
			setBanner({
				type: "success",
				message: `项目「${deleteTarget.name || deleteTarget.id}」已删除`,
			});
		} catch (err: unknown) {
			setDeleteTarget(null);
			const msg = err instanceof Error ? err.message : "删除失败，请重试";
			setBanner({ type: "error", message: msg });
		}
	};

	const allSelected =
		projects.length > 0 && selectedIds.size === projects.length;

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

	const confirmBulkDelete = async () => {
		const ids = Array.from(selectedIds);
		const results = await Promise.allSettled(
			ids.map((id) => api.deleteProject(id)),
		);
		let successCount = 0;
		let failureCount = 0;
		for (const result of results) {
			if (result.status === "fulfilled") {
				successCount++;
			} else {
				failureCount++;
			}
		}
		setShowBulkDeleteModal(false);
		setSelectedIds(new Set());
		load();
		if (failureCount === 0) {
			setBanner({
				type: "success",
				message: `已删除 ${successCount} 个项目`,
			});
		} else {
			setBanner({
				type: "error",
				message: `${successCount} 成功，${failureCount} 失败`,
			});
		}
	};

	const openCreateModal = () => {
		setCreateName("");
		setCreateError(null);
		setShowCreateModal(true);
	};

	return (
		<div>
			{/* Header */}
			<div className="flex items-center justify-between mb-6">
				<h1
					className="text-xl font-bold"
					style={{ color: "var(--text-primary)" }}
				>
					项目列表
				</h1>
				<button
					className="text-white px-4 py-2 rounded-lg text-sm font-semibold transition-all"
					style={{
						background: "var(--btn-primary-bg)",
						color: "var(--btn-primary-text)",
					}}
					onMouseEnter={(e) => {
						e.currentTarget.style.background = "var(--btn-primary-hover)";
					}}
					onMouseLeave={(e) => {
						e.currentTarget.style.background = "var(--btn-primary-bg)";
					}}
					onClick={openCreateModal}
				>
					新建项目
				</button>
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
			{selectedIds.size > 0 && (
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
						已选 {selectedIds.size} 项
					</span>
					<div className="flex gap-2">
						<button
							type="button"
							className="px-3 py-1.5 text-xs rounded-md font-medium transition-colors"
							style={{
								background: "var(--btn-danger-bg)",
								color: "var(--btn-danger-text)",
							}}
							onClick={() => setShowBulkDeleteModal(true)}
						>
							批量删除
						</button>
						<button
							type="button"
							className="px-3 py-1.5 text-xs rounded-md font-medium transition-colors"
							style={{
								background: "var(--btn-ghost-bg)",
								color: "var(--btn-ghost-text)",
								border: "1px solid var(--border-default)",
							}}
							onClick={clearSelection}
						>
							取消选择
						</button>
					</div>
				</div>
			)}

			{/* Loading state: show loading indicator, NOT empty state */}
			{loading ? (
				<div className="text-center py-16">
					<p className="text-sm" style={{ color: "var(--text-tertiary)" }}>
						加载中...
					</p>
				</div>
			) : projects.length === 0 ? (
				/* Empty state — uses same modal as header button */
				<div className="text-center py-16">
					<p
						className="text-lg font-semibold mb-2"
						style={{ color: "var(--text-primary)" }}
					>
						开始你的第一个项目
					</p>
					<p className="text-sm mb-6" style={{ color: "var(--text-tertiary)" }}>
						创建项目后，即可批量生产短视频内容
					</p>
					<button
						className="text-white px-5 py-2.5 rounded-lg text-sm font-semibold transition-all"
						style={{
							background: "var(--btn-primary-bg)",
							color: "var(--btn-primary-text)",
						}}
						onClick={openCreateModal}
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
				/* Project table */
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
											highlightId === p.id
												? "var(--accent-bg, #f0f9ff)"
												: undefined,
									}}
									onMouseEnter={(e) => {
										if (highlightId !== p.id) {
											e.currentTarget.style.background = "var(--bg-nav-active)";
										}
									}}
									onMouseLeave={(e) => {
										if (highlightId !== p.id) {
											e.currentTarget.style.background = "";
										}
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

			{/* Create Modal */}
			<Modal
				isOpen={showCreateModal}
				title="新建项目"
				onClose={() => setShowCreateModal(false)}
			>
				<div className="mb-4">
					<label
						className="block text-sm font-medium mb-2"
						style={{ color: "var(--text-primary)" }}
					>
						项目名称
					</label>
					<input
						ref={createInputRef}
						className="w-full rounded-lg px-3 py-2 text-sm border"
						style={{
							background: "var(--input-bg)",
							color: "var(--input-text)",
							borderColor: createError
								? "var(--danger)"
								: "var(--input-border)",
						}}
						placeholder="请输入项目名称"
						value={createName}
						onChange={(e) => {
							setCreateName(e.target.value);
							if (createError) setCreateError(null);
						}}
						onKeyDown={(e) => e.key === "Enter" && handleCreate()}
					/>
					{createError && (
						<p className="mt-1 text-xs" style={{ color: "var(--danger)" }}>
							{createError}
						</p>
					)}
				</div>
				<div className="flex justify-end gap-3">
					<button
						type="button"
						className="px-4 py-2 text-sm rounded-lg transition-colors"
						style={{
							background: "var(--btn-ghost-bg)",
							color: "var(--btn-ghost-text)",
							border: "1px solid var(--border-default)",
						}}
						onClick={() => setShowCreateModal(false)}
					>
						取消
					</button>
					<button
						type="button"
						className="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
						style={{
							background: "var(--btn-primary-bg)",
							color: "var(--btn-primary-text)",
						}}
						onClick={handleCreate}
					>
						创建
					</button>
				</div>
			</Modal>

			{/* Delete confirmation dialog */}
			<ConfirmDialog
				isOpen={!!deleteTarget}
				title="确认删除"
				message={
					deleteTarget
						? `确定要删除项目「${deleteTarget.name || deleteTarget.id}」吗？此操作不可撤销。`
						: ""
				}
				confirmLabel="确认删除"
				danger={true}
				onConfirm={confirmDelete}
				onCancel={() => setDeleteTarget(null)}
			/>

			{/* Bulk delete confirmation dialog */}
			<ConfirmDialog
				isOpen={showBulkDeleteModal}
				title="确认批量删除"
				message={`确定要删除选中的 ${selectedIds.size} 个项目吗？此操作不可撤销。`}
				confirmLabel="确认删除"
				danger={true}
				onConfirm={confirmBulkDelete}
				onCancel={() => setShowBulkDeleteModal(false)}
			/>
		</div>
	);
}
