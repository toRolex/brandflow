import { afterEach, describe, expect, it, vi } from "vitest";
import { initLogReporting, stopLogReporting } from "../logCapture";

describe("log capture", () => {
	afterEach(() => stopLogReporting());

	it("reports a browser error once within the dedupe window", async () => {
		const fetchMock = vi
			.spyOn(globalThis, "fetch")
			.mockResolvedValue(
				new Response(JSON.stringify({ ok: true }), { status: 200 }),
			);
		initLogReporting();
		window.dispatchEvent(new ErrorEvent("error", { message: "browser boom" }));
		window.dispatchEvent(new ErrorEvent("error", { message: "browser boom" }));
		await Promise.resolve();
		expect(fetchMock).toHaveBeenCalledTimes(1);
		fetchMock.mockRestore();
	});

	it("reports console.warn with level warn", async () => {
		const fetchMock = vi
			.spyOn(globalThis, "fetch")
			.mockResolvedValue(
				new Response(JSON.stringify({ ok: true }), { status: 200 }),
			);
		const originalWarn = vi.spyOn(console, "warn").mockImplementation(() => {});
		initLogReporting();
		console.warn("test warn");
		await Promise.resolve();
		expect(fetchMock).toHaveBeenCalledTimes(1);
		const [, request] = fetchMock.mock.calls[0];
		expect(JSON.parse(String(request?.body))).toMatchObject({
			level: "warn",
			message: "test warn",
		});
		originalWarn.mockRestore();
		fetchMock.mockRestore();
	});

	it("adds a stack when console.error receives a plain string", async () => {
		const fetchMock = vi
			.spyOn(globalThis, "fetch")
			.mockResolvedValue(
				new Response(JSON.stringify({ ok: true }), { status: 201 }),
			);
		const originalError = vi
			.spyOn(console, "error")
			.mockImplementation(() => {});
		initLogReporting();
		console.error("console boom");
		await Promise.resolve();
		const [, request] = fetchMock.mock.calls[0];
		expect(JSON.parse(String(request?.body))).toMatchObject({
			message: "console boom",
			stack_trace: expect.stringContaining("console boom"),
		});
		originalError.mockRestore();
		fetchMock.mockRestore();
	});

	it("does not dedupe errors whose full stacks differ", async () => {
		const fetchMock = vi
			.spyOn(globalThis, "fetch")
			.mockResolvedValue(
				new Response(JSON.stringify({ ok: true }), { status: 201 }),
			);
		const originalError = vi
			.spyOn(console, "error")
			.mockImplementation(() => {});
		const first = new Error("same failure");
		const second = new Error("same failure");
		first.stack = "Error: same failure\n at shared-a\n at shared-b\n at first";
		second.stack =
			"Error: same failure\n at shared-a\n at shared-b\n at second";
		initLogReporting();

		console.error(first);
		console.error(second);
		await Promise.resolve();

		expect(fetchMock).toHaveBeenCalledTimes(2);
		originalError.mockRestore();
		fetchMock.mockRestore();
	});

	it("reports uncaught errors with message and stack_trace", async () => {
		const fetchMock = vi
			.spyOn(globalThis, "fetch")
			.mockResolvedValue(
				new Response(JSON.stringify({ ok: true }), { status: 200 }),
			);
		initLogReporting();
		const error = new Error("uncaught error");
		error.stack = "Error: uncaught error\n    at test.ts:10:5";
		window.dispatchEvent(
			new ErrorEvent("error", {
				error,
				message: error.message,
				filename: "test.ts",
				lineno: 10,
				colno: 5,
			}),
		);
		await Promise.resolve();
		expect(fetchMock).toHaveBeenCalledTimes(1);
		const [, request] = fetchMock.mock.calls[0];
		expect(JSON.parse(String(request?.body))).toMatchObject({
			message: "uncaught error",
			stack_trace: "Error: uncaught error\n    at test.ts:10:5",
			extra: { url: "test.ts", line: 10, column: 5 },
		});
		fetchMock.mockRestore();
	});

	it("reports unhandled promise rejections with message", async () => {
		const fetchMock = vi
			.spyOn(globalThis, "fetch")
			.mockResolvedValue(
				new Response(JSON.stringify({ ok: true }), { status: 200 }),
			);
		initLogReporting();
		const error = new Error("unhandled rejection");
		window.dispatchEvent(
			new PromiseRejectionEvent("unhandledrejection", {
				reason: error,
				promise: Promise.resolve(),
			}),
		);
		await Promise.resolve();
		expect(fetchMock).toHaveBeenCalledTimes(1);
		const [, request] = fetchMock.mock.calls[0];
		expect(JSON.parse(String(request?.body))).toMatchObject({
			message: "unhandled rejection",
			stack_trace: expect.stringContaining("Error: unhandled rejection"),
		});
		fetchMock.mockRestore();
	});
});
