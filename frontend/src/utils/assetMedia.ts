/**
 * Normalize an asset file path into a playable media URL.
 *
 * The backend stores absolute or mixed-separator paths; the browser expects
 * a `/workspace/...` URL. This helper extracts or adds the `/workspace/`
 * prefix and normalizes Windows backslashes.
 */
export function resolveAssetMediaUrl(filePath: string): string {
	if (!filePath) {
		return filePath;
	}

	const normalizedPath = filePath.replaceAll("\\", "/");
	if (normalizedPath.startsWith("/workspace/")) {
		return normalizedPath;
	}

	const workspaceIndex = normalizedPath.indexOf("/workspace/");
	if (workspaceIndex >= 0) {
		return normalizedPath.slice(workspaceIndex);
	}

	return normalizedPath;
}
