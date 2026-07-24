import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Layout from "../Layout";

// Version display tests need mocked API
const mockCheckVersion = vi.hoisted(() => vi.fn());
const mockTriggerUpdate = vi.hoisted(() => vi.fn());
const mockGetUpdateStatus = vi.hoisted(() => vi.fn());
vi.mock("../../api/version", () => ({
	checkVersion: mockCheckVersion,
	triggerUpdate: mockTriggerUpdate,
	getUpdateStatus: mockGetUpdateStatus,
}));

function renderWithRouter(path: string) {
	return render(
		<MemoryRouter initialEntries={[path]}>
			<Layout>content</Layout>
		</MemoryRouter>,
	);
}

describe("Layout — TTS nav entries (#151)", () => {
	beforeEach(() => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.7.13",
			update_available: false,
		});
		mockGetUpdateStatus.mockResolvedValue({ status: "idle" });
	});

	it("renders sub-nav with TTS 配置 link when at /tts-config", () => {
		renderWithRouter("/tts-config");
		expect(screen.getByText("TTS 配置")).toBeInTheDocument();
	});

	it("renders TTS 配置 in sub-nav when at /config", () => {
		renderWithRouter("/config");
		expect(screen.getByText("TTS 配置")).toBeInTheDocument();
	});

	it("does not render sub-nav for non-config paths", () => {
		renderWithRouter("/");
		expect(screen.queryByText("TTS 配置")).not.toBeInTheDocument();
		expect(screen.queryByText("系统配置")).not.toBeInTheDocument();
	});

	it("renders all 4 main nav items", () => {
		renderWithRouter("/");
		expect(screen.getByTitle("项目列表")).toBeInTheDocument();
		expect(screen.getByTitle("素材库")).toBeInTheDocument();
		expect(screen.getByTitle("系统配置")).toBeInTheDocument();
		expect(screen.getByTitle("数据追踪")).toBeInTheDocument();
	});
});

describe("Layout — version display", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		sessionStorage.clear();
		mockGetUpdateStatus.mockResolvedValue({ status: "idle" });
	});

	it("shows version badge next to Brandflow", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.7.13",
			update_available: false,
		});
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByText(/v0\.7\.13/)).toBeInTheDocument();
		});
	});

	it("shows update banner when update available", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByText(/新版本可用/)).toBeInTheDocument();
		});
	});

	it("dismisses banner and does not re-show", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByText(/新版本可用/)).toBeInTheDocument();
		});

		const closeBtn = screen.getByRole("button", { name: /关闭/ });
		closeBtn.click();

		await waitFor(() => {
			expect(screen.queryByText(/新版本可用/)).not.toBeInTheDocument();
		});
	});

	it("does not show banner when up-to-date", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.7.13",
			update_available: false,
		});
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByText(/v0\.7\.13/)).toBeInTheDocument();
		});
		expect(screen.queryByText(/新版本可用/)).not.toBeInTheDocument();
	});

	it("shows green checkmark and 最新 when up-to-date", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.7.13",
			update_available: false,
		});
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByText("最新")).toBeInTheDocument();
		});
		expect(screen.getByText("✓")).toBeInTheDocument();
	});

	it("shows orange dot when update available", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByTestId("version-update-dot")).toBeInTheDocument();
		});
	});

	it("re-checks version on refresh button click", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.7.13",
			update_available: false,
		});
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByText("最新")).toBeInTheDocument();
		});

		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});

		const refreshBtn = screen.getByRole("button", {
			name: /检查更新/,
		});
		refreshBtn.click();

		await waitFor(() => {
			expect(screen.getByTestId("version-update-dot")).toBeInTheDocument();
		});
	});

	it("silently handles check-version failure", async () => {
		mockCheckVersion.mockRejectedValue(new Error("network error"));
		renderWithRouter("/");

		await new Promise((r) => setTimeout(r, 50));

		expect(screen.queryByText(/新版本可用/)).not.toBeInTheDocument();
		expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
		expect(screen.queryByText(/v0/)).not.toBeInTheDocument();
	});
});

describe("Layout — update flow with progress (#330)", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		sessionStorage.clear();
		mockGetUpdateStatus.mockResolvedValue({ status: "idle" });
	});

	it("shows update button when version is available", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument();
		});
	});

	it("shows progress bar with step label and percent on running", async () => {
		vi.useFakeTimers({ toFake: ["setInterval"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started" });
		mockGetUpdateStatus.mockReset();
		mockGetUpdateStatus.mockResolvedValueOnce({ status: "idle" });
		mockGetUpdateStatus.mockResolvedValue({
			status: "running",
			step: "compile_frontend",
			step_label: "编译前端",
			percent: 45,
		});

		renderWithRouter("/");
		await waitFor(() => {
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument();
		});

		screen.getByRole("button", { name: "更新" }).click();

		await waitFor(() => {
			expect(screen.getByTestId("update-progress-banner")).toBeInTheDocument();
		});

		// Advance past the first polling tick
		vi.advanceTimersByTime(1100);
		await act(async () => {});

		expect(screen.getByTestId("update-step-label")).toHaveTextContent(
			"编译前端",
		);
		expect(screen.getByTestId("update-percent-bar")).toBeInTheDocument();
		vi.useRealTimers();
	});

	it("shows observer message on 409 conflict", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "in_progress" });
		mockGetUpdateStatus.mockReset();
		mockGetUpdateStatus.mockResolvedValueOnce({ status: "idle" });
		mockGetUpdateStatus.mockResolvedValue({
			status: "running",
			step: "git_pull",
			step_label: "拉取最新代码",
			percent: 5,
		});

		renderWithRouter("/");
		await waitFor(() => {
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument();
		});

		screen.getByRole("button", { name: "更新" }).click();

		await waitFor(() => {
			expect(screen.getByTestId("update-step-label")).toHaveTextContent(
				/正在观察更新/,
			);
		});
	});

	it("polls progress and transitions to done", async () => {
		vi.useFakeTimers({ toFake: ["setInterval"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started" });
		mockGetUpdateStatus.mockReset();
		mockGetUpdateStatus.mockResolvedValueOnce({ status: "idle" });
		mockGetUpdateStatus.mockResolvedValueOnce({
			status: "running",
			step: "git_pull",
			step_label: "拉取最新代码",
			percent: 20,
		});
		mockGetUpdateStatus.mockResolvedValue({
			status: "done",
			step_label: "0.8.0",
		});

		renderWithRouter("/");
		await waitFor(() =>
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument(),
		);
		screen.getByRole("button", { name: "更新" }).click();

		await waitFor(() =>
			expect(screen.getByTestId("update-progress-banner")).toBeInTheDocument(),
		);

		// First poll → running
		vi.advanceTimersByTime(1100);
		await act(async () => {});
		// Second poll → done
		vi.advanceTimersByTime(1100);
		await act(async () => {});

		expect(screen.getByText(/更新完成 v0\.8\.0/)).toBeInTheDocument();
		vi.useRealTimers();
	});

	it("polls progress and transitions to restarting", async () => {
		vi.useFakeTimers({ toFake: ["setInterval"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started" });
		// Mount recovery: idle. Polling: running then restarting
		let pollCount = 0;
		mockGetUpdateStatus.mockImplementation(() => {
			pollCount++;
			if (pollCount === 1) return Promise.resolve({ status: "idle" });
			if (pollCount === 2)
				return Promise.resolve({
					status: "running",
					step: "git_pull",
					step_label: "拉取最新代码",
					percent: 20,
				});
			return Promise.resolve({
				status: "restarting",
				step: "restart",
				step_label: "重启服务",
				percent: 90,
			});
		});

		renderWithRouter("/");
		await waitFor(() =>
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument(),
		);
		screen.getByRole("button", { name: "更新" }).click();

		// The ``running`` banner appears immediately via handleUpdate's setState
		await waitFor(() =>
			expect(screen.getByTestId("update-progress-banner")).toBeInTheDocument(),
		);

		// Advance past first poll to get running step
		vi.advanceTimersByTime(1100);
		await act(async () => {});
		// Advance past second poll to get restarting
		vi.advanceTimersByTime(1100);
		await act(async () => {});

		expect(screen.getByText(/服务重启中，即将完成.../)).toBeInTheDocument();
		vi.useRealTimers();
	});

	it("polls progress and transitions to stalled", async () => {
		vi.useFakeTimers({ toFake: ["setInterval"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started" });
		let pollCount = 0;
		mockGetUpdateStatus.mockImplementation(() => {
			pollCount++;
			if (pollCount === 1) return Promise.resolve({ status: "idle" });
			if (pollCount === 2)
				return Promise.resolve({
					status: "running",
					step: "git_pull",
					step_label: "拉取最新代码",
					percent: 20,
				});
			return Promise.resolve({
				status: "running",
				step: "compile_frontend",
				step_label: "编译前端",
				percent: 30,
				stalled: true,
			});
		});

		renderWithRouter("/");
		await waitFor(() =>
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument(),
		);
		screen.getByRole("button", { name: "更新" }).click();

		await waitFor(() =>
			expect(screen.getByTestId("update-progress-banner")).toBeInTheDocument(),
		);

		vi.advanceTimersByTime(1100);
		await act(async () => {});
		vi.advanceTimersByTime(1100);
		await act(async () => {});

		expect(screen.getByText(/更新已停滞/)).toBeInTheDocument();
		vi.useRealTimers();
	});

	it("polls progress and transitions to failed with error", async () => {
		vi.useFakeTimers({ toFake: ["setInterval"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started" });
		let pollCount = 0;
		mockGetUpdateStatus.mockImplementation(() => {
			pollCount++;
			if (pollCount === 1) return Promise.resolve({ status: "idle" });
			if (pollCount === 2)
				return Promise.resolve({
					status: "running",
					step: "git_pull",
					step_label: "拉取最新代码",
					percent: 20,
				});
			return Promise.resolve({
				status: "failed",
				step: "compile_frontend",
				error: "npm install 失败",
				percent: 50,
			});
		});

		renderWithRouter("/");
		await waitFor(() =>
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument(),
		);
		screen.getByRole("button", { name: "更新" }).click();

		await waitFor(() =>
			expect(screen.getByTestId("update-progress-banner")).toBeInTheDocument(),
		);

		vi.advanceTimersByTime(1100);
		await act(async () => {});
		vi.advanceTimersByTime(1100);
		await act(async () => {});

		expect(screen.getByText(/更新失败/)).toBeInTheDocument();
		expect(screen.getByText(/npm install 失败/)).toBeInTheDocument();
		vi.useRealTimers();
	});

	it("shows done state with dismiss button", async () => {
		vi.useFakeTimers({ toFake: ["setInterval"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.8.0",
			update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started" });
		mockGetUpdateStatus.mockReset();
		mockGetUpdateStatus.mockResolvedValueOnce({ status: "idle" });
		mockGetUpdateStatus.mockResolvedValue({
			status: "done",
			step_label: "0.8.0",
		});

		renderWithRouter("/");
		await waitFor(() =>
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument(),
		);
		screen.getByRole("button", { name: "更新" }).click();

		await waitFor(() =>
			expect(screen.getByTestId("update-progress-banner")).toBeInTheDocument(),
		);

		vi.advanceTimersByTime(1100);
		await act(async () => {});

		expect(screen.getByText(/更新完成 v0\.8\.0/)).toBeInTheDocument();

		// Dismiss
		const closeBtn = screen.getByRole("button", { name: "关闭" });
		closeBtn.click();
		vi.useRealTimers();
	});
});
