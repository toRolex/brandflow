import { describe, expect, it } from "vitest";
import type { JobDetail } from "../../types";
import { getJobActionPolicy } from "../jobActionPolicy";

function job(overrides: Partial<JobDetail>): JobDetail {
	return {
		job_id: "job-1",
		project_id: "project-1",
		product: "product",
		platforms: ["douyin"],
		phase: "queued",
		review_status: "none",
		execution: {
			status: "pending",
			current_attempt: 0,
			max_attempts: 3,
			error: null,
		},
		artifacts: [],
		...overrides,
	};
}

describe("getJobActionPolicy", () => {
	it("only enables retry for a retryable failed job", () => {
		expect(getJobActionPolicy(job({ phase: "paused" })).canRetry).toBe(false);
		expect(
			getJobActionPolicy(
				job({
					phase: "failed",
					execution: {
						status: "failed",
						current_attempt: 1,
						max_attempts: 3,
						error: { code: "TEMP", message: "temporary", retryable: true },
					},
				}),
			).canRetry,
		).toBe(true);
	});

	it("explains why a non-retryable failure cannot be retried", () => {
		const policy = getJobActionPolicy(
			job({
				phase: "failed",
				execution: {
					status: "failed",
					current_attempt: 1,
					max_attempts: 3,
					error: { code: "INPUT", message: "fix input", retryable: false },
				},
			}),
		);
		expect(policy.canRetry).toBe(false);
		expect(policy.retryMessage).toContain("修复");
	});
});
