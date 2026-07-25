import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LogsPage from "../LogsPage";

const listLogDates = vi.hoisted(() => vi.fn());
vi.mock("../../api/logs", () => ({
	listLogDates,
	downloadLogUrl: (date: string) => `/api/logs/download?date=${date}`,
}));

describe("LogsPage", () => {
	it("renders each available date and its download link", async () => {
		listLogDates.mockResolvedValue([
			{ date: "2026-07-25", size_bytes: 1536, error_count: 3 },
		]);
		render(<LogsPage />);
		await waitFor(() => expect(screen.getByText("2026-07-25")).toBeInTheDocument());
		expect(screen.getByText("1.5 KB")).toBeInTheDocument();
		expect(screen.getByRole("link")).toHaveAttribute(
			"href",
			"/api/logs/download?date=2026-07-25",
		);
	});

	it("shows the empty state when no dates are available", async () => {
		listLogDates.mockResolvedValue([]);
		render(<LogsPage />);
		await waitFor(() => expect(screen.getByText("暂无运行日志")).toBeInTheDocument());
	});
});
