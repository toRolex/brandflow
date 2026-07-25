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
});
