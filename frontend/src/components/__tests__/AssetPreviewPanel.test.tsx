import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AssetRecord } from "../../types";
import AssetPreviewPanel from "../AssetPreviewPanel";

const MOCK_ASSET: AssetRecord = {
	asset_id: "test_001",
	file_path: "/workspace/shared_assets/indexed/零食产品/产品特写/test.mp4",
	category: "产品特写",
	product: "零食产品",
	confidence: 0.9,
	duration_seconds: 5.5,
	status: "available" as const,
	usage_count: 3,
	source_video: "",
	tags: ["tag1", "tag2"],
	created_at: "2025-01-01T00:00:00Z",
	last_used_at: "",
};

describe("AssetPreviewPanel", () => {
	it("renders custom categories in the edit dropdown", async () => {
		const onUpdateFields = vi.fn().mockResolvedValue(undefined);
		const customCategories = ["促销活动", "开箱展示", "产品评测"];

		const { container } = render(
			<AssetPreviewPanel
				asset={MOCK_ASSET}
				categories={customCategories}
				onUpdateFields={onUpdateFields}
			/>,
		);

		// Click edit button
		fireEvent.click(screen.getByText("编辑"));

		// The select element should exist and contain custom category options
		const select = container.querySelector("select") as HTMLSelectElement;
		expect(select).toBeInTheDocument();
		expect(select.options.length).toBe(customCategories.length);

		const optionTexts = Array.from(select.options).map((o) => o.textContent);
		for (const cat of customCategories) {
			expect(optionTexts).toContain(cat);
		}
	});

	it("saves a custom category via onUpdateFields", async () => {
		const onUpdateFields = vi.fn().mockResolvedValue(undefined);
		const customCategories = ["促销活动", "开箱展示"];

		const { container } = render(
			<AssetPreviewPanel
				asset={MOCK_ASSET}
				categories={customCategories}
				onUpdateFields={onUpdateFields}
			/>,
		);

		// Click edit
		fireEvent.click(screen.getByText("编辑"));

		// Select custom category from dropdown
		const select = container.querySelector("select") as HTMLSelectElement;
		fireEvent.change(select, { target: { value: "促销活动" } });

		// Click save
		fireEvent.click(screen.getByText("保存"));

		await waitFor(() => {
			expect(onUpdateFields).toHaveBeenCalledWith(MOCK_ASSET, {
				product: MOCK_ASSET.product,
				category: "促销活动",
			});
		});
	});

	it("renders old food categories when provided", async () => {
		const onUpdateFields = vi.fn().mockResolvedValue(undefined);
		const foodCategories = ["产地溯源", "烹饪翻炒", "产品特写"];

		const { container } = render(
			<AssetPreviewPanel
				asset={MOCK_ASSET}
				categories={foodCategories}
				onUpdateFields={onUpdateFields}
			/>,
		);

		fireEvent.click(screen.getByText("编辑"));

		const select = container.querySelector("select") as HTMLSelectElement;
		const optionTexts = Array.from(select.options).map((o) => o.textContent);
		for (const cat of foodCategories) {
			expect(optionTexts).toContain(cat);
		}
	});
});
