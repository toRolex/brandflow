export interface VersionCheckResult {
	current: string;
	latest: string;
	update_available: boolean;
}

/** Check for newer versions via the control-plane API. */
export async function checkVersion(): Promise<VersionCheckResult> {
	const resp = await fetch("/api/check-version");
	if (!resp.ok) {
		throw new Error(`check-version failed: ${resp.status}`);
	}
	return resp.json();
}
