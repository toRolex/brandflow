import { useEffect, useState } from "react";
import { downloadLogUrl, type LogDateInfo, listLogDates } from "../api/logs";

function formatSize(bytes: number): string {
	return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

export default function LogsPage() {
	const [logs, setLogs] = useState<LogDateInfo[]>([]);
	const [loading, setLoading] = useState(true);
	const [failed, setFailed] = useState(false);
	useEffect(() => {
		listLogDates()
			.then(setLogs)
			.catch(() => setFailed(true))
			.finally(() => setLoading(false));
	}, []);
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
			<h1 className="text-lg font-semibold">运行日志</h1>
			{logs.length === 0 ? (
				<p className="text-sm text-[var(--text-secondary)]">暂无运行日志</p>
			) : (
				<div className="border rounded-lg overflow-hidden border-[var(--border-default)]">
					<table className="w-full text-sm">
						<thead className="bg-[var(--bg-table-head)]">
							<tr>
								<th className="p-3 text-left">日期</th>
								<th className="p-3 text-left">文件大小</th>
								<th className="p-3 text-left">错误条数</th>
								<th className="p-3" />
							</tr>
						</thead>
						<tbody>
							{logs.map((log) => (
								<tr
									key={log.date}
									className="border-t border-[var(--border-default)]"
								>
									<td className="p-3">{log.date}</td>
									<td className="p-3">{formatSize(log.size_bytes)}</td>
									<td className="p-3">{log.error_count}</td>
									<td className="p-3 text-right">
										<a
											className="text-[var(--accent)] hover:underline"
											href={downloadLogUrl(log.date)}
											download={true}
										>
											下载
										</a>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}
		</div>
	);
}
