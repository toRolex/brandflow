import { describe, expect, it, vi } from "vitest";
import { ApiError, request } from "../core";

describe("api core", () => {
	it("sends X-Request-Id header and exposes it on ApiError", async () => {
		const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
			new Response('{"detail":"bad"}', { status: 400 }),
		);

		try {
			await request("/api/test");
			throw new Error("expected ApiError");
		} catch (e) {
			expect(e).toBeInstanceOf(ApiError);
			const err = e as ApiError;
			const [, init] = fetchMock.mock.calls[0];
			const headers = new Headers(init?.headers);
			const requestId = headers.get("X-Request-Id");
			expect(requestId).toBeTruthy();
			expect(requestId).toMatch(/^[\w-]+$/);
			expect(err.requestId).toBe(requestId);
		}

		fetchMock.mockRestore();
	});
});
