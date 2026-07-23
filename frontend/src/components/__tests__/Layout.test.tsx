import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Layout from "../Layout";

// Version display tests need mocked API
const mockCheckVersion = vi.hoisted(() => vi.fn());
const mockTriggerUpdate = vi.hoisted(() => vi.fn());
vi.mock("../../api/version", () => ({
	checkVersion: mockCheckVersion,
	triggerUpdate: mockTriggerUpdate,
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
		// Provide default mock so Layout's useEffect doesn't throw
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13",
			latest: "0.7.13",
			update_available: false,
		});
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
				expect(
					screen.getByTestId("version-update-dot"),
				).toBeInTheDocument();
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

			// Change mock response to simulate new version found
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
				expect(
					screen.getByTestId("version-update-dot"),
				).toBeInTheDocument();
			});
		});

		it("silently handles check-version failure", async () => {
		mockCheckVersion.mockRejectedValue(new Error("network error"));
		renderWithRouter("/");

		// Wait for rejection to settle through the catch handler
		await new Promise((r) => setTimeout(r, 50));

		// No error displayed, no banner shown
		expect(screen.queryByText(/新版本可用/)).not.toBeInTheDocument();
		expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
		// Version badge not shown when API fails (no version info)
		expect(screen.queryByText(/v0/)).not.toBeInTheDocument();
	});
});

describe("Layout — update flow (#302)", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		sessionStorage.clear();
	});

	it("shows update button when version is available", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13", latest: "0.8.0", update_available: true,
		});
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument();
		});
	});

	it("transitions to updating state on click", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13", latest: "0.8.0", update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started", log: "packaging/windows/update.log" });
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument();
		});

		screen.getByRole("button", { name: "更新" }).click();

		await waitFor(() => {
			expect(screen.getByText(/正在更新/)).toBeInTheDocument();
		});
	});

	it("shows in_progress message on 409", async () => {
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13", latest: "0.8.0", update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "in_progress" });
		renderWithRouter("/");

		await waitFor(() => {
			expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument();
		});

		screen.getByRole("button", { name: "更新" }).click();

		await waitFor(() => {
			expect(screen.getByText(/更新正在进行/)).toBeInTheDocument();
		});
	});

	it("polls and transitions to done when version changes", async () => {
		vi.useFakeTimers({ toFake: ["setInterval"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13", latest: "0.8.0", update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started", log: "packaging/windows/update.log" });
		renderWithRouter("/");

		await waitFor(() => expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument());
		screen.getByRole("button", { name: "更新" }).click();
		await waitFor(() => expect(screen.getByText(/正在更新/)).toBeInTheDocument());

		mockCheckVersion.mockResolvedValue({
			current: "0.8.0", latest: "0.8.0", update_available: false,
		});
		vi.advanceTimersByTime(2000);
		await act(async () => {});

		expect(screen.getByText(/更新完成/)).toBeInTheDocument();
		expect(screen.getByText(/更新完成，版本 v0\.8\.0/)).toBeInTheDocument();
		vi.useRealTimers();
	});

	it("transitions to restarting when poll fails", async () => {
		vi.useFakeTimers({ toFake: ["setInterval"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13", latest: "0.8.0", update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started", log: "packaging/windows/update.log" });
		renderWithRouter("/");

		await waitFor(() => expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument());
		screen.getByRole("button", { name: "更新" }).click();
		await waitFor(() => expect(screen.getByText(/正在更新/)).toBeInTheDocument());

		mockCheckVersion.mockRejectedValue(new Error("connection refused"));
		vi.advanceTimersByTime(2000);
		await act(async () => {});

		expect(screen.getByText(/服务重启中/)).toBeInTheDocument();
		vi.useRealTimers();
	});

	it("recovers from restarting to done when version changes", async () => {
		vi.useFakeTimers({ toFake: ["setInterval"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13", latest: "0.8.0", update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started", log: "packaging/windows/update.log" });
		renderWithRouter("/");

		await waitFor(() => expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument());
		screen.getByRole("button", { name: "更新" }).click();
		await waitFor(() => expect(screen.getByText(/正在更新/)).toBeInTheDocument());

		mockCheckVersion.mockRejectedValue(new Error("connection refused"));
		vi.advanceTimersByTime(2000);
		await act(async () => {});
		expect(screen.getByText(/服务重启中/)).toBeInTheDocument();

		mockCheckVersion.mockResolvedValue({
			current: "0.8.0", latest: "0.8.0", update_available: false,
		});
		vi.advanceTimersByTime(2000);
		await act(async () => {});

		await waitFor(() => {
			expect(screen.getByText(/更新完成/)).toBeInTheDocument();
		});
		vi.useRealTimers();
	});

	it("transitions to failed after 5 minute timeout", async () => {
		vi.useFakeTimers({ toFake: ["setInterval", "Date"] });
		mockCheckVersion.mockResolvedValue({
			current: "0.7.13", latest: "0.8.0", update_available: true,
		});
		mockTriggerUpdate.mockResolvedValue({ status: "started", log: "packaging/windows/update.log" });
		renderWithRouter("/");

		await waitFor(() => expect(screen.getByRole("button", { name: "更新" })).toBeInTheDocument());
		screen.getByRole("button", { name: "更新" }).click();
		await waitFor(() => expect(screen.getByText(/正在更新/)).toBeInTheDocument());

		vi.advanceTimersByTime(302_000);
		await act(async () => {});

		expect(screen.getByText(/更新失败/)).toBeInTheDocument();
		expect(screen.getByText(/packaging\/windows\/update\.log/)).toBeInTheDocument();
		vi.useRealTimers();
	});
});
