import { describe, expect, it } from "vitest";

import { shouldPollJob } from "../jobPollingPolicy";

describe("shouldPollJob", () => {
	it.each([
		"queued",
		"script_generating",
		"script_review",
		"tts_generating",
		"asset_review",
		"final_review",
	] as const)("keeps polling an active %s job", (phase) => {
		expect(shouldPollJob(phase)).toBe(true);
	});

	it.each([
		"draft",
		"paused",
		"failed",
		"cancelled",
		"completed",
	] as const)("stops polling a stable %s job", (phase) => {
		expect(shouldPollJob(phase)).toBe(false);
	});
});
