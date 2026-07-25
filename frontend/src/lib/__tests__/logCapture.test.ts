import { afterEach, describe, expect, it, vi } from "vitest";
import { initLogReporting, stopLogReporting } from "../logCapture";

describe("log capture", () => {
	afterEach(() => stopLogReporting());

	it("reports a browser error once within the dedupe window", async () => {
		const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
			new Response(JSON.stringify({ ok: true }), { status: 200 }),
		);
		initLogReporting();
		window.dispatchEvent(new ErrorEvent("error", { message: "browser boom" }));
		window.dispatchEvent(new ErrorEvent("error", { message: "browser boom" }));
		await Promise.resolve();
		expect(fetchMock).toHaveBeenCalledTimes(1);
		fetchMock.mockRestore();
	});

	it("preserves an Error stack reported through console.error", async () => {
		const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
			new Response(JSON.stringify({ ok: true }), { status: 201 }),
		);
		const originalError = vi.spyOn(console, "error").mockImplementation(() => {});
		initLogReporting();
		console.error(new Error("console boom"));
		await Promise.resolve();
		const [, request] = fetchMock.mock.calls[0];
		expect(JSON.parse(String(request?.body))).toMatchObject({
			message: "console boom",
			stack_trace: expect.stringContaining("console boom"),
		});
		originalError.mockRestore();
		fetchMock.mockRestore();
	});
});
