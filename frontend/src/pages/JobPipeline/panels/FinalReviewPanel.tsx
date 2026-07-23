import MediaPlayer from "../../../components/MediaPlayer";
import PhaseStatusNotice from "./PhaseStatusNotice";
import type { PanelProps } from "../types";

export default function FinalReviewPanel({
	isCurrentReviewStep,
	onApprove,
	onReject,
	findArtifact,
	getPhasePresentation,
}: PanelProps) {
	const finalVideo = findArtifact("final_video");
	const presentation = getPhasePresentation("final_review");
	const hasIntegrityError = presentation.kind === "integrity_error";
	return (
		<div>
			<h3 className="font-semibold text-sm mb-3">终审 · 烧录</h3>
			{hasIntegrityError ? (
				<PhaseStatusNotice presentation={presentation} />
			) : (
				<MediaPlayer src={finalVideo?.url || ""} kind="video" />
			)}
			{!isCurrentReviewStep && (
				<div
					className="text-xs mb-2"
					style={{ color: "var(--color-caution-amber)" }}
				>
					当前不在该审核阶段，无法操作
				</div>
			)}
			<div className="flex gap-2 mt-4">
				<button
					className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
					onClick={() => onApprove("final_review")}
					disabled={!isCurrentReviewStep || hasIntegrityError}
					aria-disabled={!isCurrentReviewStep || hasIntegrityError}
				>
					{"✓"} 通过
				</button>
				<button
					className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
					onClick={() => onReject("final_review")}
					disabled={!isCurrentReviewStep || hasIntegrityError}
					aria-disabled={!isCurrentReviewStep || hasIntegrityError}
				>
					{"✗"} 打回
				</button>
			</div>
		</div>
	);
}
