import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ClipReviewCard from "../ClipReviewCard";

it("opens asset selection from an unresolved clip", () => {
	const onSelectAsset = vi.fn();
	render(
		<ClipReviewCard
			clip={{
				sentence: "需要人工决策",
				category: "产品",
				file_path: "",
				asset_id: "",
				method: "",
				visual_type: "unresolved",
			}}
			index={2}
			onReject={() => {}}
			onToggleBlank={() => {}}
			onRestore={() => {}}
			onSelectAsset={onSelectAsset}
		/>,
	);

	fireEvent.click(screen.getByRole("button", { name: "选择素材" }));
	expect(onSelectAsset).toHaveBeenCalledWith(2);
});

it("shows searching overlay and disables actions while re-searching", () => {
	render(
		<ClipReviewCard
			clip={{
				sentence: "示例文案",
				category: "产品",
				file_path: "/workspace/shared_assets/clip.mp4",
				asset_id: "asset-1",
				method: "llm_match",
				visual_type: "clip",
			}}
			index={0}
			searching={true}
			onReject={() => {}}
			onToggleBlank={() => {}}
			onRestore={() => {}}
			onSelectAsset={() => {}}
		/>,
	);

	expect(screen.getByText("检索中")).toBeInTheDocument();
	expect(screen.getByText("正在重新检索素材…")).toBeInTheDocument();

	const buttons = screen.getAllByRole("button");
	for (const button of buttons) {
		expect(button).toBeDisabled();
	}
});
