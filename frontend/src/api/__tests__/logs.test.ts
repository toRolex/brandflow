import { describe, expect, it, vi } from "vitest";
import { listLogDates, reportError } from "../logs";

describe("log API", () => {
	it("sends frontend errors to the log endpoint", async () => {
		const fetchMock = vi
			.spyOn(globalThis, "fetch")
			.mockResolvedValue(
				new Response(JSON.stringify({ ok: true }), { status: 200 }),
			);
		await reportError({ source: "frontend", level: "error", message: "boom" });
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/logs/error",
			expect.objectContaining({ method: "POST" }),
		);
		fetchMock.mockRestore();
	});

	it("loads daily log metadata", async () => {
		const page = {
			items: [{ date: "2026-07-25", size_bytes: 100, error_count: 1 }],
			total: 1,
			page: 1,
			page_size: 50,
		};
		const fetchMock = vi
			.spyOn(globalThis, "fetch")
			.mockResolvedValue(new Response(JSON.stringify(page), { status: 200 }));
		await expect(listLogDates()).resolves.toEqual(page);
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/logs/dates?page=1&page_size=50",
			expect.anything(),
		);
		fetchMock.mockRestore();
	});
});
