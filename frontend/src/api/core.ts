const BASE = "";

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		...init,
		headers: { "Content-Type": "application/json", ...init?.headers },
	});
	if (!res.ok) {
		const text = await res.text();
		throw new Error(`${res.status}: ${text}`);
	}
	return res.json() as Promise<T>;
}

export async function uploadFile<T>(path: string, file: File): Promise<T> {
	const form = new FormData();
	form.append("file", file);
	const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
	if (!res.ok) {
		const text = await res.text();
		throw new Error(`${res.status}: ${text}`);
	}
	return res.json() as Promise<T>;
}
