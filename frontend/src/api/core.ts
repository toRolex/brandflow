const BASE = "";

class ApiError extends Error {
	readonly detail: string;
	readonly status: number;
	readonly retryAfterSeconds: number | null;

	constructor(
		status: number,
		message: string,
		retryAfterSecondsValue: number | null = null,
	) {
		super(`${status}: ${message}`);
		this.name = "ApiError";
		this.status = status;
		this.retryAfterSeconds = retryAfterSecondsValue;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		...init,
		headers: { "Content-Type": "application/json", ...init?.headers },
	});
	if (!res.ok) {
		const text = await res.text();
		throw new ApiError(res.status, text, retryAfterSeconds(res));
	}
	return res.json() as Promise<T>;
}

async function uploadFile<T>(path: string, file: File): Promise<T> {
	const form = new FormData();
	form.append("file", file);
	const res = await fetch(path, { method: "POST", body: form });
	if (!res.ok) {
		const text = await res.text();
		throw new ApiError(res.status, text, retryAfterSeconds(res));
	}
	return res.json() as Promise<T>;
}

const DEFAULT_PAGE_SIZE = 10;

export { ApiError, DEFAULT_PAGE_SIZE, request, uploadFile };
