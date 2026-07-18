import type { VideoMetric } from "../types";

const SORT_OPTIONS = [
	{ value: "plays_desc", label: "播放量" },
	{ value: "likes_desc", label: "点赞" },
	{ value: "completion_desc", label: "完播率" },
	{ value: "followers_desc", label: "涨粉" },
	{ value: "date_desc", label: "发布日期" },
];

const PLATFORM_OPTIONS = [
	{ value: "", label: "全部平台" },
	{ value: "weixin", label: "视频号" },
	{ value: "xiaohongshu", label: "小红书" },
];

function platformTag(p: string) {
	if (p === "weixin")
		return (
			<span className="inline-block px-2 py-0.5 text-xs rounded-full bg-[var(--bg-tag-green)] text-[var(--text-tag-green)] border border-[var(--success-border)]">
				视频号
			</span>
		);
	return (
		<span className="inline-block px-2 py-0.5 text-xs rounded-full bg-[var(--alert-red-muted)] text-[var(--alert-red)] border border-[var(--danger-border)]">
			小红书
		</span>
	);
}

function formatNum(v: number): string {
	if (v >= 10000) return (v / 10000).toFixed(1) + "万";
	return v.toLocaleString();
}

interface Props {
	videos: VideoMetric[];
	total: number;
	loading: boolean;
	sortBy: string;
	onSortChange: (s: string) => void;
	onSearchChange: (q: string) => void;
	onPlatformChange: (p: string) => void;
	onAssetClick: (v: VideoMetric) => void;
}

export default function VideoTable({
	videos,
	total,
	loading,
	sortBy,
	onSortChange,
	onSearchChange,
	onPlatformChange,
	onAssetClick,
}: Props) {
	return (
		<div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-card)]">
			{/* Header */}
			<div className="flex items-center gap-3 p-4 border-b border-[var(--border-subtle)] flex-wrap">
				<span className="text-sm font-medium text-[var(--text-primary)]">
					视频列表
					<span className="ml-2 text-xs text-[var(--text-tertiary)]">
						({total})
					</span>
				</span>
				<input
					type="text"
					placeholder="搜索标题..."
					onChange={(e) => onSearchChange(e.target.value)}
					className="ml-auto w-full sm:w-auto px-3 py-1.5 text-sm border border-[var(--border-default)] rounded-lg focus:outline-none focus:border-[var(--color-electric-blue)]"
				/>
				<select
					onChange={(e) => onPlatformChange(e.target.value)}
					className="px-2 py-1.5 text-sm border border-[var(--border-default)] rounded-lg"
				>
					{PLATFORM_OPTIONS.map((o) => (
						<option key={o.value} value={o.value}>
							{o.label}
						</option>
					))}
				</select>
				<select
					value={sortBy}
					onChange={(e) => onSortChange(e.target.value)}
					className="px-2 py-1.5 text-sm border border-[var(--border-default)] rounded-lg"
				>
					{SORT_OPTIONS.map((o) => (
						<option key={o.value} value={o.value}>
							排序: {o.label}
						</option>
					))}
				</select>
			</div>

			{/* Table */}
			<div className="overflow-auto max-h-[600px]">
				<table className="w-full text-sm">
					<thead className="sticky top-0 bg-[var(--bg-table-head)] text-[var(--text-secondary)] text-xs uppercase">
						<tr>
							<th className="px-3 py-2 text-left w-10">#</th>
							<th className="px-3 py-2 text-left">标题</th>
							<th className="px-3 py-2 text-left">平台</th>
							<th className="px-3 py-2 text-right">播放量</th>
							<th className="px-3 py-2 text-right">点赞</th>
							<th className="px-3 py-2 text-right">评论</th>
							<th className="px-3 py-2 text-right">分享</th>
							<th className="px-3 py-2 text-center">完播率</th>
							<th className="px-3 py-2 text-right">涨粉</th>
							<th className="px-3 py-2 text-left">素材</th>
							<th className="px-3 py-2 text-left">发布日期</th>
						</tr>
					</thead>
					<tbody>
						{loading ? (
							<tr>
								<td
									colSpan={11}
									className="p-8 text-center text-[var(--text-tertiary)]"
								>
									加载中...
								</td>
							</tr>
						) : videos.length === 0 ? (
							<tr>
								<td
									colSpan={11}
									className="p-8 text-center text-[var(--text-tertiary)]"
								>
									暂无数据
								</td>
							</tr>
						) : (
							videos.map((v, i) => (
								<tr
									key={v.id}
									className="border-t border-[var(--border-subtle)] hover:bg-[var(--bg-nav-active)]"
								>
									<td className="px-3 py-2 text-[var(--text-tertiary)]">
										{i + 1}
									</td>
									<td className="px-3 py-2 max-w-[220px] truncate text-[var(--text-primary)]">
										{v.title}
									</td>
									<td className="px-3 py-2">{platformTag(v.platform)}</td>
									<td className="px-3 py-2 text-right">{formatNum(v.plays)}</td>
									<td className="px-3 py-2 text-right">{formatNum(v.likes)}</td>
									<td className="px-3 py-2 text-right">
										{formatNum(v.comments)}
									</td>
									<td className="px-3 py-2 text-right">
										{formatNum(v.shares)}
									</td>
									<td className="px-3 py-2">
										{v.completion_rate != null ? (
											<div className="flex items-center gap-1 justify-center">
												<div className="w-16 h-1.5 bg-[var(--bg-table-head)] rounded-full overflow-hidden">
													<div
														className="h-full bg-[var(--color-electric-blue)] rounded-full"
														style={{
															width: `${Math.min(v.completion_rate, 100)}%`,
														}}
													/>
												</div>
												<span className="text-xs text-[var(--text-secondary)]">
													{v.completion_rate.toFixed(0)}%
												</span>
											</div>
										) : (
											<span className="text-xs text-[var(--text-tertiary)]">
												-
											</span>
										)}
									</td>
									<td className="px-3 py-2 text-right">
										{v.followers_gained > 0 ? (
											<span className="text-[var(--color-signal-green)]">
												+{v.followers_gained}
											</span>
										) : (
											<span className="text-[var(--text-tertiary)]">
												{v.followers_gained}
											</span>
										)}
									</td>
									<td className="px-3 py-2">
										{v.used_asset_ids.length > 0 ? (
											<button
												onClick={() => onAssetClick(v)}
												className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full border border-[var(--success-border)] text-[var(--text-tag-green)] hover:bg-[var(--bg-tag-green)] cursor-pointer"
											>
												{v.used_asset_ids.length} 个 ▸
											</button>
										) : (
											<span className="text-xs text-[var(--text-tertiary)]">
												未关联
											</span>
										)}
									</td>
									<td className="px-3 py-2 text-[var(--text-secondary)]">
										{v.publish_date}
									</td>
								</tr>
							))
						)}
					</tbody>
				</table>
			</div>
		</div>
	);
}
