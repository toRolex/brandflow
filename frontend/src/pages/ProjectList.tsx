import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Project } from "../types";

export default function ProjectList() {
	const [projects, setProjects] = useState<Project[]>([]);
	const [newName, setNewName] = useState("");
	const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
	const inputRef = useRef<HTMLInputElement>(null);
	const navigate = useNavigate();

	const load = () => {
		api
			.listProjects()
			.then(setProjects)
			.catch(() => setProjects([]));
	};

	useEffect(() => {
		load();
	}, []);

	const create = async () => {
		if (!newName.trim()) return;
		try {
			const p = await api.createProject(newName.trim());
			setNewName("");
			navigate(`/projects/${p.id}`);
		} catch {
			// silently fail
		}
	};

	const confirmDelete = async () => {
		if (!deleteTarget) return;
		try {
			await api.deleteProject(deleteTarget.id);
			setDeleteTarget(null);
			load();
		} catch {
			// silently fail
		}
	};

	const focusInput = () => {
		inputRef.current?.focus();
	};

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

			{projects.length === 0 ? (
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
									style={{ borderColor: "var(--border-default)" }}
									onMouseEnter={(e) => {
										e.currentTarget.style.background = "var(--bg-nav-active)";
									}}
									onMouseLeave={(e) => {
										e.currentTarget.style.background = "";
									}}
								>
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

			{deleteTarget && (
				<div
					className="fixed inset-0 flex items-center justify-center"
					style={{
						background: "rgba(0, 0, 0, 0.5)",
						zIndex: "var(--z-modal-backdrop)",
					}}
				>
					<div
						className="max-w-sm w-full mx-4 p-6 border"
						style={{
							background: "var(--bg-card)",
							borderColor: "var(--border-default)",
							borderRadius: "var(--radius-lg)",
							boxShadow: "var(--shadow-modal)",
						}}
					>
						<h3
							className="text-lg font-bold mb-2"
							style={{ color: "var(--text-primary)" }}
						>
							确认删除
						</h3>
						<p
							className="mb-6 text-sm"
							style={{ color: "var(--text-secondary)" }}
						>
							确定要删除项目「{deleteTarget.name || deleteTarget.id}
							」吗？此操作不可撤销。
						</p>
						<div className="flex justify-end gap-3">
							<button
								className="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
								style={{
									background: "var(--btn-ghost-bg)",
									color: "var(--btn-ghost-text)",
								}}
								onClick={() => setDeleteTarget(null)}
								onMouseEnter={(e) => {
									e.currentTarget.style.background =
										"var(--btn-ghost-hover-bg)";
								}}
								onMouseLeave={(e) => {
									e.currentTarget.style.background = "var(--btn-ghost-bg)";
								}}
							>
								取消
							</button>
							<button
								className="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
								style={{
									background: "var(--btn-danger-bg)",
									color: "var(--btn-danger-text)",
								}}
								onClick={confirmDelete}
								onMouseEnter={(e) => {
									e.currentTarget.style.background = "var(--btn-danger-hover)";
								}}
								onMouseLeave={(e) => {
									e.currentTarget.style.background = "var(--btn-danger-bg)";
								}}
							>
								确认删除
							</button>
						</div>
					</div>
				</div>
			)}
		</div>
	);
}
