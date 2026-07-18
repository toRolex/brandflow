import ReactECharts from "echarts-for-react";
import type { MetricsOverview } from "../types";

export default function TrendChart({ data }: { data: MetricsOverview | null }) {
	if (!data || data.daily.length === 0) {
		return (
			<div className="rounded-xl border border-gray-200 bg-white p-8 text-center text-gray-400">
				暂无数据
			</div>
		);
	}

	const dates = data.daily.map((d) => d.publish_date);
	const plays = data.daily.map((d) => d.plays);
	const likes = data.daily.map((d) => d.likes);
	const followers = data.daily.map((d) => d.followers);

	const option = {
		tooltip: { trigger: "axis" as const },
		legend: { data: ["播放量", "点赞", "涨粉"], top: 4 },
		grid: { top: 40, bottom: 30, left: 60, right: 60 },
		xAxis: {
			type: "category" as const,
			data: dates,
			axisLabel: { fontSize: 11 },
		},
		yAxis: [
			{
				type: "value" as const,
				name: "播放量",
				position: "left" as const,
				axisLabel: { fontSize: 11 },
			},
			{
				type: "value" as const,
				name: "互动",
				position: "right" as const,
				axisLabel: { fontSize: 11 },
			},
		],
		series: [
			{
				name: "播放量",
				type: "line",
				smooth: true,
				areaStyle: { opacity: 0.15 },
				data: plays,
				yAxisIndex: 0,
			},
			{
				name: "点赞",
				type: "line",
				smooth: true,
				data: likes,
				yAxisIndex: 1,
			},
			{
				name: "涨粉",
				type: "line",
				smooth: true,
				data: followers,
				yAxisIndex: 1,
			},
		],
	};

	return (
		<div className="rounded-xl border border-gray-200 bg-white p-4 w-full">
			<ReactECharts option={option} style={{ height: 320 }} />
		</div>
	);
}
