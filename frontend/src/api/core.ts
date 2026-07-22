const BASE = "";

export class ApiError extends Error {
	constructor(
		public readonly status: number,
		message: string,
		public readonly retryAfterSeconds: number | null = null,
	) {
		super(`${status}: ${message}`);
		this.name = "ApiError";
	}
}

function retryAfterSeconds(response: Response): number | null {
	const value = Number(response.headers.get("Retry-After"));
	return Number.isFinite(value) && value > 0 ? value : null;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
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

export async function uploadFile<T>(path: string, file: File): Promise<T> {
	const form = new FormData();
	form.append("file", file);
	const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
	if (!res.ok) {
		const text = await res.text();
		throw new ApiError(res.status, text, retryAfterSeconds(res));
	}
	return res.json() as Promise<T>;
}
