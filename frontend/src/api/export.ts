export const downloadExport = async (jobId: string) => {
	const res = await fetch(`/api/jobs/${jobId}/export`);
	if (!res.ok) {
		const text = await res.text();
		throw new Error(`${res.status}: ${text}`);
	}
	return res.blob();
};
