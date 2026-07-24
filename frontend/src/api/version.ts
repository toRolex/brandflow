export interface VersionCheckResult {
	current: string;
	latest: string;
	update_available: boolean;
}

/** Check for newer versions via the control-plane API. */
export async function checkVersion(): Promise<VersionCheckResult> {
	const resp = await fetch(`/api/check-version?_=${Date.now()}`, {
		cache: "no-store",
	});
	if (!resp.ok) {
		throw new Error(`check-version failed: ${resp.status}`);
	}
	return resp.json();
}

export interface TriggerUpdateResult {
	status: "started" | "in_progress";
	log?: string;
}

/** Trigger a one-click update on the control-plane. */
export async function triggerUpdate(): Promise<TriggerUpdateResult> {
	const resp = await fetch("/api/update", { method: "POST" });
	if (resp.status === 409) return { status: "in_progress" };
	if (!resp.ok) throw new Error(`update failed: ${resp.status}`);
	return resp.json();
}

export interface UpdateStatus {
	status: "idle" | "running" | "restarting" | "done" | "failed";
	step?: string;
	step_label?: string;
	percent?: number;
	error?: string;
	updated_at?: string;
	stalled?: boolean;
}

/** Poll the current update progress from the control-plane. */
export async function getUpdateStatus(): Promise<UpdateStatus> {
	const resp = await fetch("/api/update/status", { cache: "no-store" });
	if (!resp.ok) throw new Error(`update status failed: ${resp.status}`);
	return resp.json();
}
