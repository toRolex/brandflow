import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Layout from "../Layout";

// Version display tests need mocked API
const mockCheckVersion = vi.hoisted(() => vi.fn());
vi.mock("../../api/version", () => ({
	checkVersion: mockCheckVersion,
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
