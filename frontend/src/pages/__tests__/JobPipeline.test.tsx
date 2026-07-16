import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../api/client";
import JobPipeline from "../JobPipeline";

vi.mock("../../api/client", () => ({
  api: {
    getJob: vi.fn(),
    retryJob: vi.fn(),
    pauseJob: vi.fn(),
    getJobLogs: vi.fn(),
  },
}));

vi.mock("../../components/PipelineSidebar", () => ({ default: () => <aside /> }));

const failedJob = {
  job_id: "job-170",
  project_id: "project-1",
  product: "product",
  platforms: ["douyin"],
  phase: "failed" as const,
  failed_phase: "video_rendering" as const,
  review_status: "none" as const,
  artifacts: [],
  execution: {
    status: "failed" as const,
    current_attempt: 3,
    max_attempts: 3,
    error: {
      code: "VIDEO_SOURCE_MISSING",
      message: "No usable video source is available.",
      retryable: false,
    },
  },
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/jobs/job-170"]}>
      <Routes><Route path="/jobs/:id" element={<JobPipeline />} /></Routes>
    </MemoryRouter>,
  );
}

describe("JobPipeline execution failure workflow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getJob).mockResolvedValue(failedJob);
    vi.mocked(api.retryJob).mockResolvedValue({ status: "phase_queued_for_retry" });
  });

  it("shows actionable structured failure details", async () => {
    renderPage();

    expect(await screen.findByText("VIDEO_SOURCE_MISSING")).toBeInTheDocument();
    expect(screen.getByText("No usable video source is available.")).toBeInTheDocument();
    expect(screen.getByText(/video_rendering/)).toBeInTheDocument();
    expect(screen.getByText(/3 \/ 3/)).toBeInTheDocument();
  });

  it("awaits retry and reloads the recovered phase", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "重试失败阶段" }));

    await waitFor(() => expect(api.retryJob).toHaveBeenCalledWith("job-170"));
    await waitFor(() => expect(api.getJob).toHaveBeenCalledTimes(2));
  });

  it("shows retry request failures", async () => {
    vi.mocked(api.retryJob).mockRejectedValue(new Error("still invalid"));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "重试失败阶段" }));

    expect(await screen.findByText("重试前验证失败")).toBeInTheDocument();
  });

  it("surfaces structured 409 revalidation detail from the server", async () => {
    vi.mocked(api.retryJob).mockRejectedValue(
      new Error(
        `409: ${JSON.stringify({
          detail: {
            code: "VIDEO_SOURCE_MISSING",
            message: "No usable video source is available.",
            retryable: false,
          },
        })}`,
      ),
    );
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "重试失败阶段" }));

    expect(
      await screen.findByText(
        "重试前验证失败：No usable video source is available.（VIDEO_SOURCE_MISSING）",
      ),
    ).toBeInTheDocument();
  });

  it("shows bounded retry progress while the phase remains active", async () => {
    vi.mocked(api.getJob).mockResolvedValue({
      ...failedJob,
      phase: "video_rendering",
      failed_phase: undefined,
      execution: {
        status: "retrying",
        current_attempt: 2,
        max_attempts: 3,
        error: null,
      },
    });
    renderPage();

    expect(await screen.findByText(/正在重试，第 2 \/ 3 次/)).toBeInTheDocument();
  });
});
