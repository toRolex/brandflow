import ScriptPreview from "../../../components/ScriptPreview";
import type { PanelProps } from "../types";
import PhaseStatusNotice from "./PhaseStatusNotice";

export default function ScriptPanel({
	job,
	activeStepKey,
	scriptContent,
	isCurrentReviewStep,
	onApprove,
	onReject,
	onRetry,
	onEditScript,
	onRegenerateWithPrompt,
	findArtifact,
	getPhasePresentation,
}: PanelProps) {
	const scriptArtifact = findArtifact("script");
	const presentation = getPhasePresentation(
		activeStepKey === "script_gen" ? "script_generating" : "script_review",
		activeStepKey === "script_gen" ? {} : { requiredArtifacts: ["script"] },
	);
	const hasIntegrityError = presentation.kind === "integrity_error";
	if (hasIntegrityError) {
		return <PhaseStatusNotice presentation={presentation} />;
	}
	return (
		<ScriptPreview
			script={scriptContent || (scriptArtifact ? "加载中..." : "等待生成...")}
			checks={null}
			brand={job.brand}
			mode={job.mode}
			reviewEnabled={isCurrentReviewStep && !!scriptArtifact}
			onApprove={() => onApprove("script_review")}
			onReject={() => onReject("script_review")}
			onRegenerate={onRetry}
			onEdit={onEditScript}
			onRegenerateWithPrompt={onRegenerateWithPrompt}
		/>
	);
}
