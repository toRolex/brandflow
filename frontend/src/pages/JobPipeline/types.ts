import type { ExportTaskState, JobDetail, Phase, SceneFolder } from "../../types";

export interface TTSVoice {
	id: string;
	label: string;
	note: string;
	model: string;
}

export interface TTSVoiceInfo {
	model: string;
	voice: string;
	resolved_from: string;
	product: string;
}

export interface PanelProps {
	job: JobDetail;
	activeStepKey: string;
	scriptContent: string;
	selectedClips: Record<string, unknown>[];
	rejectedClips: Set<number>;
	showAllBlankConfirm: boolean;
	sceneFolders: SceneFolder[];
	selectedSceneFolders: string[];
	ttsVoices: TTSVoice[];
	ttsVoiceInfo: TTSVoiceInfo | null;
	ttsSelectedModel: string;
	ttsSelectedVoice: string;
	ttsPreviewUrl: string;
	ttsPreviewLoading: boolean;
	showVoiceConfirm: boolean;
	pendingVoiceChange: { model?: string; voice?: string } | null;
	ttsVoiceError: string;
	exportTask: ExportTaskState | null;
	exportCreating: boolean;
	exportDownloading: boolean;
	isCurrentReviewStep: boolean;
	onApprove: (gate: string) => void;
	onReject: (gate: string) => void;
	onRetry: () => void;
	onEditScript: (script: string) => void;
	onRegenerateWithPrompt: (prompt: string) => void;
	onMigrateScenes: () => void;
	onCreateExport: () => void;
	onDownloadExport: () => void;
	onSceneFolderToggle: (path: string, checked: boolean) => void;
	onTtsModelChange: (model: string) => void;
	onTtsVoiceChange: (voice: string) => void;
	onTtsPreview: () => void;
	onApplyVoiceChange: (model?: string, voice?: string) => void;
	onConfirmVoiceChange: () => void;
	onCancelVoiceChange: () => void;
	onRejectClip: (index: number) => void;
	onToggleBlank: (index: number) => void;
	onRestoreClip: (index: number) => void;
	onAssetApprove: () => void;
	onForceApprove: () => void;
	onDismissAllBlankConfirm: () => void;
	findArtifact: (kind: string) =>
		| { kind: string; relative_path: string; url: string }
		| undefined;
}

export { JobDetail, Phase, SceneFolder };
