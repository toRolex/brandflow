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
