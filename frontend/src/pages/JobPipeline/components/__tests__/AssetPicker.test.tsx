import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { listIndexedAssetsShared } from "../../../../api/assetLibrary";
import type { AssetRecord } from "../../../../types/asset";
import AssetPicker from "../AssetPicker";

vi.mock("../../../../api/assetLibrary", () => ({
	listIndexedAssetsShared: vi.fn(),
}));

const mockAssets: AssetRecord[] = [
	{
		asset_id: "asset-1",
		file_path: "/workspace/shared_assets/clip1.mp4",
		category: "产品展示",
		product: "p1",
		confidence: 0.92,
		duration_seconds: 12.5,
		status: "available",
		usage_count: 0,
		source_video: "source1.mp4",
		tags: [],
		created_at: "2026-07-28T00:00:00Z",
		last_used_at: "2026-07-28T00:00:00Z",
	},
	{
		asset_id: "asset-2",
		file_path: "/workspace/shared_assets/clip2.mp4",
		category: "使用场景",
		product: "p1",
		confidence: 0.85,
		duration_seconds: 8.0,
		status: "available",
		usage_count: 1,
		source_video: "source2.mp4",
		tags: [],
		created_at: "2026-07-28T00:00:00Z",
		last_used_at: "2026-07-28T00:00:00Z",
	},
	{
		asset_id: "asset-3",
		file_path: "/workspace/shared_assets/clip3.mp4",
		category: "产品展示",
		product: "p1",
		confidence: 0.78,
		duration_seconds: 15.2,
		status: "disabled",
		usage_count: 0,
		source_video: "source3.mp4",
		tags: [],
		created_at: "2026-07-28T00:00:00Z",
		last_used_at: "2026-07-28T00:00:00Z",
	},
];

describe("AssetPicker", () => {
	const onSelect = vi.fn();
	const onCancel = vi.fn();

	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(listIndexedAssetsShared).mockResolvedValue({
			assets: mockAssets,
			stats: {
				total: 3,
				available: 2,
				disabled: 1,
				source_videos: 1,
				category_counts: {},
				duration_min: 0,
				duration_max: 0,
				usage_min: 0,
				usage_max: 0,
			},
			page: 1,
			pageSize: mockAssets.length,
			total: mockAssets.length,
		});
	});

	it("loads shared assets and filters by available status", async () => {
		render(
			<AssetPicker product="p1" onSelect={onSelect} onCancel={onCancel} />,
		);

		await waitFor(() => {
			expect(listIndexedAssetsShared).toHaveBeenCalledWith({
				product: "p1",
			});
		});

		// asset-3 is disabled and should be filtered out
		expect(screen.getByText("clip1.mp4")).toBeInTheDocument();
		expect(screen.getByText("clip2.mp4")).toBeInTheDocument();
		expect(screen.queryByText("clip3.mp4")).not.toBeInTheDocument();
	});

	it("applies preferred category filter on open", async () => {
		render(
			<AssetPicker
				product="p1"
				preferredCategory="产品展示"
				onSelect={onSelect}
				onCancel={onCancel}
			/>,
		);

		await screen.findByText("clip1.mp4");
		expect(screen.queryByText("clip2.mp4")).not.toBeInTheDocument();
		expect(screen.getByText("共 1 个素材")).toBeInTheDocument();
	});

	it("filters assets by selected category", async () => {
		render(
			<AssetPicker product="p1" onSelect={onSelect} onCancel={onCancel} />,
		);

		await screen.findByText("clip1.mp4");

		fireEvent.change(screen.getByRole("combobox"), {
			target: { value: "使用场景" },
		});

		expect(screen.queryByText("clip1.mp4")).not.toBeInTheDocument();
		expect(screen.getByText("clip2.mp4")).toBeInTheDocument();
	});

	it("disables confirm button until an asset is selected", async () => {
		render(
			<AssetPicker product="p1" onSelect={onSelect} onCancel={onCancel} />,
		);

		const confirmBtn = await screen.findByRole("button", { name: "确认选择" });
		expect(confirmBtn).toBeDisabled();

		fireEvent.click(screen.getByText("clip1.mp4"));
		expect(confirmBtn).not.toBeDisabled();

		fireEvent.click(confirmBtn);
		expect(onSelect).toHaveBeenCalledWith(mockAssets[0]);
	});

	it("renders a video preview for the selected asset", async () => {
		render(
			<AssetPicker product="p1" onSelect={onSelect} onCancel={onCancel} />,
		);

		await screen.findByText("clip1.mp4");
		fireEvent.click(screen.getByText("clip1.mp4"));

		await waitFor(() => {
			const video = document.querySelector("video");
			expect(video).toBeInTheDocument();
			expect(video?.querySelector("source")).toHaveAttribute(
				"src",
				"/workspace/shared_assets/clip1.mp4",
			);
		});
	});

	it("calls onCancel when cancel button is clicked", async () => {
		render(
			<AssetPicker product="p1" onSelect={onSelect} onCancel={onCancel} />,
		);

		await screen.findByText("clip1.mp4");
		const cancelButtons = screen.getAllByRole("button", { name: "取消" });
		fireEvent.click(cancelButtons[0]);
		expect(onCancel).toHaveBeenCalled();
	});
});
