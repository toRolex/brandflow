import {
	act,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { VideoMetric, VideoMetricPage } from "../../types";
import AnalyticsPage from "../AnalyticsPage";

vi.mock("../../api/client", () => ({
	api: {
		getMetricsOverview: vi.fn(),
		getMetricsTopics: vi.fn(),
		getMetricsVideos: vi.fn(),
		uploadMetrics: vi.fn(),
		scanMetrics: vi.fn(),
	},
}));

function video(id: number, title: string): VideoMetric {
	return {
		id,
		platform: "weixin",
		title,
		platform_id: null,
		publish_date: "2026-07-26",
		content_type: "",
		plays: 0,
		likes: 0,
		comments: 0,
		shares: 0,
		followers_gained: 0,
		completion_rate: null,
		avg_watch_duration: null,
		exposure: 0,
		cover_click_rate: null,
		favorites: 0,
		danmaku: 0,
		forward_count: 0,
		job_id: null,
		used_asset_ids: [],
	};
}

function page(
	items: VideoMetric[],
	currentPage: number,
	total = 20,
): VideoMetricPage {
	return { items, total, page: currentPage, page_size: 10 };
}

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((done) => {
		resolve = done;
	});
	return { promise, resolve };
}

describe("AnalyticsPage pagination", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.spyOn(window, "alert").mockImplementation(() => {});
		vi.mocked(api.getMetricsOverview).mockResolvedValue({
			total_plays: 0,
			total_likes: 0,
			total_followers: 0,
			avg_completion: 0,
			video_count: 0,
			daily: [],
		});
		vi.mocked(api.getMetricsTopics).mockResolvedValue([]);
	});

	it("keeps the newest video response when an older page request finishes later", async () => {
		const oldPage = deferred<VideoMetricPage>();
		const newestSearch = deferred<VideoMetricPage>();
		vi.mocked(api.getMetricsVideos)
			.mockResolvedValueOnce(page([video(1, "第一页")], 1))
			.mockReturnValueOnce(oldPage.promise)
			.mockReturnValueOnce(newestSearch.promise);

		render(<AnalyticsPage />);
		await waitFor(() => expect(screen.getByText("第一页")).toBeInTheDocument());

		fireEvent.click(screen.getByRole("button", { name: "下一页" }));
		fireEvent.change(screen.getByPlaceholderText("搜索标题..."), {
			target: { value: "最新" },
		});

		newestSearch.resolve(page([video(3, "最新搜索结果")], 1, 1));
		await waitFor(() =>
			expect(screen.getByText("最新搜索结果")).toBeInTheDocument(),
		);

		oldPage.resolve(page([video(2, "过期第二页")], 2));
		await Promise.resolve();

		expect(screen.getByText("最新搜索结果")).toBeInTheDocument();
		expect(screen.queryByText("过期第二页")).not.toBeInTheDocument();
	});

	it("keeps the newest overview when an older filter request finishes later", async () => {
		const oldOverview =
			deferred<Awaited<ReturnType<typeof api.getMetricsOverview>>>();
		const newestOverview =
			deferred<Awaited<ReturnType<typeof api.getMetricsOverview>>>();
		vi.mocked(api.getMetricsOverview)
			.mockResolvedValueOnce({
				total_plays: 1,
				total_likes: 0,
				total_followers: 0,
				avg_completion: 0,
				video_count: 0,
				daily: [],
			})
			.mockReturnValueOnce(oldOverview.promise)
			.mockReturnValueOnce(newestOverview.promise);
		vi.mocked(api.getMetricsVideos).mockResolvedValue(page([], 1, 0));

		render(<AnalyticsPage />);
		await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());

		fireEvent.click(screen.getByRole("button", { name: "1天" }));
		fireEvent.click(screen.getByRole("button", { name: "30天" }));

		await act(async () => {
			newestOverview.resolve({
				total_plays: 300,
				total_likes: 0,
				total_followers: 0,
				avg_completion: 0,
				video_count: 0,
				daily: [],
			});
		});
		await waitFor(() => expect(screen.getByText("300")).toBeInTheDocument());

		await act(async () => {
			oldOverview.resolve({
				total_plays: 100,
				total_likes: 0,
				total_followers: 0,
				avg_completion: 0,
				video_count: 0,
				daily: [],
			});
		});

		expect(screen.getByText("300")).toBeInTheDocument();
		expect(
			screen.queryByText("100", { selector: "div" }),
		).not.toBeInTheDocument();
	});

	it("shows global row numbers across pages", async () => {
		vi.mocked(api.getMetricsVideos)
			.mockResolvedValueOnce(page([video(1, "第一页")], 1))
			.mockResolvedValueOnce(page([video(11, "第二页")], 2));

		render(<AnalyticsPage />);
		await waitFor(() => expect(screen.getByText("第一页")).toBeInTheDocument());
		fireEvent.click(screen.getByRole("button", { name: "下一页" }));

		await waitFor(() => expect(screen.getByText("第二页")).toBeInTheDocument());
		expect(screen.getByText("11")).toBeInTheDocument();
	});

	it("refreshes uploaded data with the latest filters", async () => {
		const upload = deferred<Awaited<ReturnType<typeof api.uploadMetrics>>>();
		vi.mocked(api.uploadMetrics).mockReturnValue(upload.promise);
		vi.mocked(api.getMetricsVideos).mockResolvedValue(page([], 1, 0));

		const { container } = render(<AnalyticsPage />);
		await waitFor(() =>
			expect(api.getMetricsOverview).toHaveBeenCalledWith(7, undefined),
		);

		const fileInput =
			container.querySelector<HTMLInputElement>('input[type="file"]');
		expect(fileInput).not.toBeNull();
		fireEvent.change(fileInput!, {
			target: { files: [new File(["data"], "metrics.csv")] },
		});
		fireEvent.click(screen.getByRole("button", { name: "1天" }));
		await waitFor(() =>
			expect(api.getMetricsOverview).toHaveBeenCalledWith(1, undefined),
		);

		await act(async () => {
			upload.resolve({ inserted: 1, updated: 0 });
		});

		await waitFor(() => {
			const calls = vi.mocked(api.getMetricsOverview).mock.calls;
			expect(calls.at(-1)).toEqual([1, undefined]);
		});
	});
});
