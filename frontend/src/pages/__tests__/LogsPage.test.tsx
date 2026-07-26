import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LogsPage from "../LogsPage";

const listLogDates = vi.hoisted(() => vi.fn());
const deleteLogDate = vi.hoisted(() => vi.fn());
const batchDeleteLogDates = vi.hoisted(() => vi.fn());
const cleanupLogs = vi.hoisted(() => vi.fn());

vi.mock("../../api/logs", () => ({
	listLogDates,
	deleteLogDate,
	batchDeleteLogDates,
	cleanupLogs,
	downloadLogUrl: (date: string) => `/api/logs/download?date=${date}`,
}));

function makePage(
	items: Array<{ date: string; size_bytes: number; error_count: number }>,
	overrides?: { page?: number; page_size?: number; total?: number },
) {
	return {
		items,
		total: overrides?.total ?? items.length,
		page: overrides?.page ?? 1,
		page_size: overrides?.page_size ?? 50,
	};
}

describe("LogsPage — deletion & pagination", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("renders each available date and its download link", async () => {
		listLogDates.mockResolvedValue(
			makePage([{ date: "2026-07-25", size_bytes: 1536, error_count: 3 }]),
		);
		render(<LogsPage />);
		await waitFor(() =>
			expect(screen.getByText("2026-07-25")).toBeInTheDocument(),
		);
		expect(screen.getByText("1.5 KB")).toBeInTheDocument();
		const link = screen.getByRole("link");
		expect(link).toHaveAttribute("download");
		expect(link).toHaveAttribute("href", "/api/logs/download?date=2026-07-25");
	});

	it("shows the empty state when no dates are available", async () => {
		listLogDates.mockResolvedValue(makePage([]));
		render(<LogsPage />);
		await waitFor(() =>
			expect(screen.getByText("暂无运行日志")).toBeInTheDocument(),
		);
	});

	it("disables today's single-delete control and explains why", async () => {
		const now = new Date();
		const today = [
			now.getFullYear(),
			String(now.getMonth() + 1).padStart(2, "0"),
			String(now.getDate()).padStart(2, "0"),
		].join("-");
		listLogDates.mockResolvedValue(
			makePage([{ date: today, size_bytes: 100, error_count: 1 }]),
		);

		render(<LogsPage />);

		await waitFor(() => expect(screen.getByText(today)).toBeInTheDocument());
		const deleteButton = screen.getByRole("button", { name: "删除" });
		expect(deleteButton).toBeDisabled();
		expect(deleteButton).toHaveAttribute("title", "当天日志受保护，无法删除");
	});

	it("single delete shows banner and reloads", async () => {
		listLogDates
			.mockResolvedValueOnce(
				makePage([{ date: "2026-07-25", size_bytes: 100, error_count: 1 }]),
			)
			.mockResolvedValueOnce(makePage([]));
		deleteLogDate.mockResolvedValue({ date: "2026-07-25", deleted: true });

		render(<LogsPage />);
		await waitFor(() =>
			expect(screen.getByText("2026-07-25")).toBeInTheDocument(),
		);

		await userEvent.click(screen.getByText("删除"));
		const confirmBtn = screen.getByRole("button", { name: "确认删除" });
		await userEvent.click(confirmBtn);

		await waitFor(() => {
			expect(deleteLogDate).toHaveBeenCalledWith("2026-07-25");
		});
		expect(screen.getByText("暂无运行日志")).toBeInTheDocument();
	});

	it("single delete for not-found is idempotent and does not wrongly adjust page", async () => {
		listLogDates
			.mockResolvedValueOnce(
				makePage([{ date: "2026-07-25", size_bytes: 100, error_count: 1 }]),
			)
			.mockResolvedValueOnce(
				makePage([{ date: "2026-07-25", size_bytes: 100, error_count: 1 }]),
			);
		deleteLogDate.mockResolvedValue({ date: "2026-07-25", deleted: false });

		render(<LogsPage />);
		await waitFor(() =>
			expect(screen.getByText("2026-07-25")).toBeInTheDocument(),
		);

		await userEvent.click(screen.getByText("删除"));
		const confirmBtn = screen.getByRole("button", { name: "确认删除" });
		await userEvent.click(confirmBtn);

		await waitFor(() => {
			expect(listLogDates).toHaveBeenCalledTimes(2);
		});
		expect(screen.getByText("2026-07-25")).toBeInTheDocument();
	});

	it("batch delete uses actual deleted count for page adjustment", async () => {
		const dates = ["2026-07-24", "2026-07-25"];
		listLogDates
			.mockResolvedValueOnce(
				makePage(
					dates.map((d) => ({ date: d, size_bytes: 100, error_count: 0 })),
				),
			)
			.mockResolvedValueOnce(makePage([]));
		batchDeleteLogDates.mockResolvedValue({
			deleted: ["2026-07-24"],
			not_found: ["2026-07-25"],
			protected: [],
		});

		render(<LogsPage />);
		await waitFor(() =>
			expect(screen.getByText("2026-07-24")).toBeInTheDocument(),
		);

		const checkboxes = screen.getAllByRole("checkbox");
		await userEvent.click(checkboxes[0]); // select all
		await userEvent.click(screen.getByText("删除选中"));
		const confirmBtn = screen.getByRole("button", { name: "确认删除" });
		await userEvent.click(confirmBtn);

		await waitFor(() => {
			expect(batchDeleteLogDates).toHaveBeenCalledWith(dates);
		});
		expect(listLogDates).toHaveBeenCalledTimes(2);
		expect(screen.getByText("1 成功，1 不存在")).toBeInTheDocument();
	});

	it("cleanup returns from an emptied last page to the new last page", async () => {
		const firstPageItem = {
			date: "2026-07-25",
			size_bytes: 50,
			error_count: 0,
		};
		const lastPageItem = {
			date: "2026-07-20",
			size_bytes: 50,
			error_count: 0,
		};
		listLogDates
			.mockResolvedValueOnce(makePage([firstPageItem], { total: 51 }))
			.mockResolvedValueOnce(makePage([lastPageItem], { page: 2, total: 51 }))
			.mockResolvedValueOnce(makePage([firstPageItem], { total: 50 }));
		cleanupLogs.mockResolvedValue({
			deleted: ["2026-07-20"],
			deleted_count: 1,
		});

		render(<LogsPage />);
		await waitFor(() =>
			expect(screen.getByText("2026-07-25")).toBeInTheDocument(),
		);
		await userEvent.click(screen.getByRole("button", { name: "2" }));
		await waitFor(() =>
			expect(screen.getByText("2026-07-20")).toBeInTheDocument(),
		);

		const cleanupButtons = screen.getAllByRole("button", { name: "清理" });
		await userEvent.click(cleanupButtons[0]);

		await waitFor(() => {
			expect(
				screen.getByText(/确定要清理.*天前的所有日志/),
			).toBeInTheDocument();
		});

		const confirmBtn = screen.getByRole("button", { name: "确认删除" });
		await userEvent.click(confirmBtn);

		await waitFor(() => {
			expect(cleanupLogs).toHaveBeenCalled();
		});
		await waitFor(() => expect(listLogDates).toHaveBeenLastCalledWith(1, 50));
		expect(screen.getByText("2026-07-25")).toBeInTheDocument();
	});
});
