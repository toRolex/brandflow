import type { Phase } from "../types";

const POLLING_PHASES = new Set<Phase>([
	"queued",
	"script_generating",
	"script_review",
	"scene_assembling",
	"tts_generating",
	"tts_review",
	"subtitle_generating",
	"asset_retrieving",
	"asset_review",
	"montage_assembling",
	"video_rendering",
	"final_rendering",
	"final_review",
]);

/** Whether this Job can change without a user-initiated action. */
export function shouldPollJob(phase: Phase): boolean {
	return POLLING_PHASES.has(phase);
}
