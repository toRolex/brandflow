import ScriptPreview from "../../../components/ScriptPreview";
import { PanelProps } from "../types";

export default function ScriptPanel({
	job,
	scriptContent,
	isCurrentReviewStep,
	onApprove,
	onReject,
	onRetry,
	onEditScript,
	onRegenerateWithPrompt,
	findArtifact,
}: PanelProps) {
	const scriptArtifact = findArtifact("script");
	return (
		<ScriptPreview
			script={
				scriptContent || (scriptArtifact ? "加载中..." : "等待生成...")
			}
			checks={null}
			brand={job.brand}
			mode={job.mode}
			reviewEnabled={isCurrentReviewStep}
			onApprove={() => onApprove("script_review")}
			onReject={() => onReject("script_review")}
			onRegenerate={onRetry}
			onEdit={onEditScript}
			onRegenerateWithPrompt={onRegenerateWithPrompt}
		/>
	);
}
