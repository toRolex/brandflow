const BASE = "";

class ApiError extends Error {
	readonly detail: string;
	readonly status: number;
	readonly retryAfterSeconds: number | null;
	readonly requestId: string | null;

	constructor(
		status: number,
		message: string,
		retryAfterSecondsValue: number | null = null,
		requestId: string | null = null,
	) {
		super(`${status}: ${message}`);
		this.name = "ApiError";
		this.status = status;
		this.retryAfterSeconds = retryAfterSecondsValue;
		this.requestId = requestId;
		this.detail = ApiError.extractDetail(message);
	}

	private static extractDetail(message: string): string {
		try {
			const parsed = JSON.parse(message);
			if (typeof parsed?.detail === "string") {
				return parsed.detail;
			}
			if (typeof parsed?.detail?.message === "string") {
				if (parsed.detail.code) {
					return `${parsed.detail.message}（${parsed.detail.code}）`;
				}
				return parsed.detail.message;
			}
		} catch {
			// Not JSON — fall back to the raw text.
		}
		return message;
	}
}

function retryAfterSeconds(response: Response): number | null {
	const value = Number(response.headers.get("Retry-After"));
	if (Number.isFinite(value) && value > 0) {
		return value;
	}
	return null;
}

function newRequestId(): string {
	if (
		typeof globalThis.crypto !== "undefined" &&
		globalThis.crypto.randomUUID
	) {
		return globalThis.crypto.randomUUID();
	}
	return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const requestId = newRequestId();
	// Correlation IDs are generated per request by the transport layer so that
	// backend logs can reliably associate a frontend request with its errors.
	// Callers should not supply their own X-Request-Id header.
	const res = await fetch(`${BASE}${path}`, {
		...init,
		headers: {
			"Content-Type": "application/json",
			...init?.headers,
			"X-Request-Id": requestId,
		},
	});
	if (!res.ok) {
		const text = await res.text();
		throw new ApiError(res.status, text, retryAfterSeconds(res), requestId);
	}
	return res.json() as Promise<T>;
}

async function uploadFile<T>(path: string, file: File): Promise<T> {
	const form = new FormData();
	form.append("file", file);
	const requestId = newRequestId();
	const res = await fetch(path, {
		method: "POST",
		body: form,
		headers: { "X-Request-Id": requestId },
	});
	if (!res.ok) {
		const text = await res.text();
		throw new ApiError(res.status, text, retryAfterSeconds(res), requestId);
	}
	return res.json() as Promise<T>;
}

const DEFAULT_PAGE_SIZE = 10;

export { ApiError, DEFAULT_PAGE_SIZE, request, uploadFile };
