import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import PipelineSidebar from "../../components/PipelineSidebar";
import { getJobActionPolicy } from "../../policies/jobActionPolicy";
import { shouldPollJob } from "../../policies/jobPollingPolicy";
import type { ExportTaskState, JobDetail, Phase } from "../../types";
import { PIPELINE_STEPS } from "../../types";
import AssetRetrievingPanel from "./panels/AssetRetrievingPanel";
import AssetReviewPanel from "./panels/AssetReviewPanel";
import CompletedPanel from "./panels/CompletedPanel";
import { FinalRenderPanel, MontagePanel } from "./panels/ExecutionPanels";
import FailedPanel from "./panels/FailedPanel";
import FinalReviewPanel from "./panels/FinalReviewPanel";
import QueuedPanel from "./panels/QueuedPanel";
import SceneAssemblyPanel from "./panels/SceneAssemblyPanel";
import ScriptPanel from "./panels/ScriptPanel";
import SubtitlePanel from "./panels/SubtitlePanel";
import { CancelledPanel, PausedPanel } from "./panels/TerminalPanels";
import TtsPanel from "./panels/TtsPanel";
import TtsReviewPanel from "./panels/TtsReviewPanel";
import VideoBasePanel from "./panels/VideoBasePanel";
import { presentPhaseStatus } from "./phasePresentation";

const EXPORT_POLL_INTERVAL_MS = 2000;

export function phaseToStepKey(phase: Phase): string {
	const step = PIPELINE_STEPS.find((candidate) => candidate.phase === phase);
	if (!step) {
		console.warn(`phaseToStepKey: no step found for phase "${phase}"`);
	}
	return step?.key ?? "";
}

function getApiErrorDetail(error: unknown): string | null {
	if (!(error instanceof Error)) return null;
	const match = error.message.match(/^\d+:\s*([\s\S]*)$/);
	if (!match) return null;
	try {
		const detail = JSON.parse(match[1])?.detail;
		if (typeof detail === "string") return detail;
		if (typeof detail?.message === "string") {
			return detail.code
				? `${detail.message}（${detail.code}）`
				: detail.message;
		}
	} catch {
		return null;
	}
	return null;
}

function computeCompletedPhases(currentPhase: Phase): Phase[] {
	const terminalPhases: Phase[] = [
		"completed",
		"failed",
		"cancelled",
		"paused",
	];
	const nonTerminalSteps = PIPELINE_STEPS.filter(
		(s) => !terminalPhases.includes(s.phase),
	);
	if (terminalPhases.includes(currentPhase)) {
		if (currentPhase === "completed") {
			return [...nonTerminalSteps.map((s) => s.phase), "completed"];
		}
		return [currentPhase];
	}
	const order = PIPELINE_STEPS.map((s) => s.phase);
	const idx = order.indexOf(currentPhase);
	if (idx <= 0) return [];
	return order
		.slice(0, idx)
		.filter((p, i, arr) => arr.indexOf(p) === i) as Phase[];
}

export default function JobPipeline() {
	const { id } = useParams<{ id: string }>();
	const navigate = useNavigate();
	const [job, setJob] = useState<JobDetail | null>(null);
	const [activeStepKey, setActiveStepKey] = useState("");
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState("");
	const [scriptContent, setScriptContent] = useState("");
	const [selectedClips, setSelectedClips] = useState<Record<string, unknown>[]>(
		[],
	);
	const [selectedClipsLoadState, setSelectedClipsLoadState] = useState<
		"idle" | "loading" | "ready" | "failed"
	>("idle");
	const [rejectedClips, setRejectedClips] = useState<Set<number>>(new Set());
	const [showAllBlankConfirm, setShowAllBlankConfirm] = useState(false);
	const initialLoad = useRef(true);

	const [ttsVoices, setTtsVoices] = useState<
		Array<{ id: string; label: string; note: string; model: string }>
	>([]);
	const [ttsVoiceInfo, setTtsVoiceInfo] = useState<{
		model: string;
		voice: string;
		resolved_from: string;
		product: string;
	} | null>(null);
	const [ttsSelectedModel, setTtsSelectedModel] = useState("");
	const [ttsSelectedVoice, setTtsSelectedVoice] = useState("");
	const [ttsPreviewUrl, setTtsPreviewUrl] = useState("");
	const [ttsPreviewLoading, setTtsPreviewLoading] = useState(false);
	const [showVoiceConfirm, setShowVoiceConfirm] = useState(false);
	const [pendingVoiceChange, setPendingVoiceChange] = useState<{
		model?: string;
		voice?: string;
	} | null>(null);
	const [ttsVoiceError, setTtsVoiceError] = useState("");

	const [exportTask, setExportTask] = useState<ExportTaskState | null>(null);
	const [exportCreating, setExportCreating] = useState(false);
	const [exportDownloading, setExportDownloading] = useState(false);

	const load = useCallback(async () => {
		if (!id) return;
		try {
			const j = await api.getJob(id);
			setJob(j);
			if (initialLoad.current) {
				setActiveStepKey(phaseToStepKey(j.phase));
				initialLoad.current = false;
			}
			setError("");
		} catch (e) {
			console.error("getJob failed", e);
			setError("加载 Job 失败");
		}
		setLoading(false);
	}, [id]);

	useEffect(() => {
		load();
	}, [load]);

	useEffect(() => {
		if (!id || !job || !shouldPollJob(job.phase)) return;
		const t = setInterval(load, 10_000);
		return () => clearInterval(t);
	}, [id, job, load]);

	const prevPhaseRef = useRef(job?.phase);
	useEffect(() => {
		if (!job) return;
		if (job.phase !== prevPhaseRef.current) {
			prevPhaseRef.current = job.phase;
			setActiveStepKey(phaseToStepKey(job.phase));
		}
	}, [job?.phase]);

	useEffect(() => {
		if (!job) return;
		const scriptArtifact = job.artifacts?.find((a) => a.kind === "script");
		if (scriptArtifact?.url) {
			fetch(scriptArtifact.url)
				.then((r) => r.text())
				.then(setScriptContent)
				.catch(() => setScriptContent(""));
		} else {
			setScriptContent("");
		}
	}, [job, job?.artifacts]);

	useEffect(() => {
		if (!job) return;
		const clipsArtifact = job.artifacts?.find(
			(a) => a.kind === "selected_clips",
		);
		if (clipsArtifact?.url) {
			setSelectedClipsLoadState("loading");
			fetch(clipsArtifact.url)
				.then((r) => r.json())
				.then((data) => {
					setSelectedClips(Array.isArray(data) ? data : []);
					setSelectedClipsLoadState("ready");
				})
				.catch(() => {
					setSelectedClips([]);
					setSelectedClipsLoadState("failed");
				});
		} else {
			setSelectedClips([]);
			setSelectedClipsLoadState("idle");
		}
	}, [job, job?.artifacts]);

	useEffect(() => {
		if (!job || !id) return;
		if (activeStepKey !== "tts" && activeStepKey !== "tts_review") return;
		api
			.getJobTTSVoice(id)
			.then((info) => {
				setTtsVoiceInfo(info);
				setTtsSelectedModel(info.model);
				setTtsSelectedVoice(info.voice);
			})
			.catch(() => {});
	}, [id, activeStepKey, job?.tts_model, job?.tts_voice]);

	useEffect(() => {
		if (!ttsSelectedModel) return;
		api
			.getTTSVoices(undefined, ttsSelectedModel)
			.then((data) => setTtsVoices(data.preset_voices))
			.catch(() => setTtsVoices([]));
	}, [ttsSelectedModel]);

	useEffect(() => {
		if (!id) return;
		let cancelled = false;
		setExportTask(null);

		const checkExport = async () => {
			try {
				const task = await api.getExportStatus(id);
				if (cancelled) return;
				setExportTask(task);
			} catch (statusError) {
				console.warn("export status poll failed", statusError);
			}
		};

		checkExport();

		const interval = setInterval(() => {
			if (cancelled) return;
			checkExport();
		}, EXPORT_POLL_INTERVAL_MS);

		return () => {
			cancelled = true;
			clearInterval(interval);
		};
	}, [id]);

	const isCurrentReviewStep = useMemo(() => {
		if (!job) return false;
		const step = PIPELINE_STEPS.find((s) => s.key === activeStepKey);
		if (!step || !step.isReview) return false;
		return job.phase === step.phase;
	}, [activeStepKey, job, job?.phase]);

	if (loading) {
		return (
			<div className="text-center py-12 text-[var(--text-tertiary)]">
				加载中...
			</div>
		);
	}

	if (!job) {
		return (
			<div className="text-center py-12">
				<p className="text-[var(--text-tertiary)] text-sm mb-2">Job 未找到</p>
				{error && <p className="text-[var(--alert-red)] text-xs">{error}</p>}
			</div>
		);
	}

	const handleApprove = async (gate: string) => {
		if (!isCurrentReviewStep) {
			setError("当前不在该审核阶段，无法操作");
			return;
		}
		try {
			await api.approveReview(job.job_id, gate);
			load();
		} catch (e) {
			console.error("approve failed", e);
			const detail = getApiErrorDetail(e);
			setError(detail || "审核操作失败");
		}
	};

	const handleReject = async (gate: string) => {
		if (!isCurrentReviewStep) {
			setError("当前不在该审核阶段，无法操作");
			return;
		}
		try {
			await api.rejectReview(job.job_id, gate);
			load();
		} catch (e) {
			console.error("reject failed", e);
			const detail = getApiErrorDetail(e);
			setError(detail || "审核操作失败");
		}
	};

	const formatRetryError = (e: unknown): string => {
		const fallback = "重试前验证失败";
		const detail = getApiErrorDetail(e);
		return detail ? `${fallback}：${detail}` : fallback;
	};

	const handleRetry = async () => {
		try {
			await api.retryJob(job.job_id);
			await load();
		} catch (e) {
			console.error("retry failed", e);
			setError(formatRetryError(e));
		}
	};

	const handlePause = async () => {
		try {
			await api.pauseJob(job.job_id);
			await load();
		} catch (e) {
			setError(getApiErrorDetail(e) || "暂停请求失败");
		}
	};

	const handleResume = async () => {
		try {
			await api.resumeJob(job.job_id);
			await load();
		} catch (e) {
			setError(getApiErrorDetail(e) || "继续任务失败");
		}
	};

	const handleCancel = async () => {
		try {
			await api.cancelJob(job.job_id);
			await load();
		} catch (e) {
			setError(getApiErrorDetail(e) || "取消请求失败");
		}
	};

	const handleEditScript = async (newScript: string) => {
		try {
			await api.editScript(job.job_id, newScript, job.project_id);
			load();
		} catch (e) {
			console.error("edit script failed", e);
			setError("编辑脚本失败");
		}
	};

	const handleRegenerateWithPrompt = async (prompt: string) => {
		try {
			await api.regenerateWithPrompt(job.job_id, prompt, job.project_id);
			load();
		} catch (e) {
			console.error("regenerate with prompt failed", e);
			setError("重新生成失败");
		}
	};

	const handleCreateExport = async () => {
		if (!job) return;
		setExportCreating(true);
		setExportDownloading(false);
		try {
			const resp = await api.createExport(job.job_id);
			setExportTask({
				task_id: resp.task_id,
				status: resp.status,
				progress: 0,
				error: null,
			});
			try {
				const task = await api.getExportStatus(job.job_id);
				if (task) setExportTask(task);
			} catch (statusError) {
				console.warn("export task created; status refresh failed", statusError);
			}
		} catch (e) {
			console.error("create export failed", e);
			setError(getApiErrorDetail(e) || "创建导出任务失败");
		} finally {
			setExportCreating(false);
		}
	};

	const handleDownloadExport = async () => {
		if (!job) return;
		setExportDownloading(true);
		try {
			const blob = await api.downloadExport(job.job_id);
			const url = URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = url;
			a.download = `${job.name || job.job_id}_export.zip`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
		} catch (e) {
			console.error("download export failed", e);
			setError("下载导出包失败");
		} finally {
			setExportDownloading(false);
		}
	};

	const handleTtsPreview = async () => {
		if (!job) return;
		setTtsPreviewLoading(true);
		try {
			const url = await api.previewJobTTS(job.job_id);
			setTtsPreviewUrl(url);
		} catch (e) {
			console.error("tts preview failed", e);
			setError("试听失败");
		}
		setTtsPreviewLoading(false);
	};

	const handleTtsVoiceChange = (model?: string, voice?: string) => {
		if (!model && !voice) return;
		const hasAudio = job?.artifacts?.some((a) => a.kind === "tts_audio");
		if (hasAudio) {
			setPendingVoiceChange({
				model: model || ttsSelectedModel,
				voice: voice || ttsSelectedVoice,
			});
			setShowVoiceConfirm(true);
			return;
		}
		applyVoiceChange(model, voice);
	};

	const applyVoiceChange = async (model?: string, voice?: string) => {
		if (!job) return;
		setTtsVoiceError("");
		try {
			const info = await api.updateJobTTSVoice(job.job_id, {
				model: model || undefined,
				voice: voice || undefined,
				confirm: false,
			});
			setTtsVoiceInfo(info);
			setTtsSelectedModel(info.model);
			setTtsSelectedVoice(info.voice);
			if (ttsPreviewUrl) {
				URL.revokeObjectURL(ttsPreviewUrl);
				setTtsPreviewUrl("");
			}
		} catch (e: unknown) {
			if (e instanceof Error && e.message.includes("409")) {
				setPendingVoiceChange({ model, voice });
				setShowVoiceConfirm(true);
				return;
			}
			if (e instanceof Error && e.message.includes("422")) {
				try {
					const body = JSON.parse(e.message.replace(/^\d+:\s*/, ""));
					setTtsVoiceError(
						typeof body.detail === "string" ? body.detail : "音色与模型不匹配",
					);
				} catch {
					setTtsVoiceError("音色与模型不匹配");
				}
				return;
			}
			console.error("voice change failed", e);
			setError("更换音色失败");
		}
	};

	const handleConfirmVoiceChange = async () => {
		if (!job || !pendingVoiceChange) return;
		try {
			const info = await api.updateJobTTSVoice(job.job_id, {
				model: pendingVoiceChange.model || undefined,
				voice: pendingVoiceChange.voice || undefined,
				confirm: true,
			});
			setTtsVoiceInfo(info);
			setTtsSelectedModel(info.model);
			setTtsSelectedVoice(info.voice);
			if (ttsPreviewUrl) {
				URL.revokeObjectURL(ttsPreviewUrl);
				setTtsPreviewUrl("");
			}
			setShowVoiceConfirm(false);
			setPendingVoiceChange(null);
			load();
		} catch (e) {
			console.error("confirm voice change failed", e);
			setError("确认更换音色失败");
		}
	};

	const handleCancelVoiceChange = () => {
		setShowVoiceConfirm(false);
		setPendingVoiceChange(null);
	};

	const findArtifact = (kind: string) =>
		job.artifacts?.find((a) => a.kind === kind);
	const executionPhase = job.phase === "failed" ? job.failed_phase : job.phase;
	const executionPhaseIndex = PIPELINE_STEPS.findIndex(
		(step) => step.phase === executionPhase,
	);

	const getPhasePresentation = (
		phase: Phase,
		options: {
			requiredArtifacts?: string[];
			artifactLoadState?: "idle" | "loading" | "ready" | "failed";
		} = {},
	) =>
		presentPhaseStatus({
			phase,
			execution:
				executionPhase === phase
					? job.execution
					: {
							status:
								PIPELINE_STEPS.findIndex((step) => step.phase === phase) >
								executionPhaseIndex
									? "pending"
									: "succeeded",
							current_attempt: 0,
							max_attempts: 0,
							error: null,
						},
			reviewStatus: job.phase === phase ? job.review_status : "none",
			artifacts: job.artifacts,
			...options,
		});

	const handleTtsModelChange = (model: string) => {
		setTtsSelectedModel(model);
		setTtsVoiceError("");
	};

	const handleTtsVoiceSelectChange = (voice: string) => {
		setTtsSelectedVoice(voice);
		setTtsVoiceError("");
	};

	const handleRejectClip = async (clipIndex: number) => {
		try {
			await api.rejectClip(job.job_id, clipIndex, job.project_id);
			setRejectedClips((prev) => new Set([...prev, clipIndex]));
			load();
		} catch (e) {
			console.error("reject clip failed", e);
			setError("打回素材失败");
		}
	};

	const handleToggleBlank = async (clipIndex: number) => {
		const clip = selectedClips[clipIndex];
		const currentVisualType = String(clip.visual_type || "");
		try {
			if (currentVisualType === "blank") {
				await api.assetRestore(job.job_id, clipIndex, job.project_id);
			} else {
				await api.assetSetBlank(job.job_id, clipIndex, job.project_id);
			}
			load();
		} catch (e) {
			console.error("toggle blank failed", e);
			setError("留空操作失败");
		}
	};

	const handleRestoreClip = async (clipIndex: number) => {
		try {
			await api.assetRestore(job.job_id, clipIndex, job.project_id);
			load();
		} catch (e) {
			console.error("restore clip failed", e);
			setError("恢复素材失败");
		}
	};

	const handleSelectAsset = async (clipIndex: number, assetId: string) => {
		try {
			await api.assetSetAsset(job.job_id, clipIndex, assetId, job.project_id);
			load();
		} catch (e) {
			console.error("select asset failed", e);
			setError("选择素材失败");
		}
	};

	const handleAssetApprove = () => {
		const allBlank =
			selectedClips.length > 0 &&
			selectedClips.every((c) => String(c.visual_type || "") === "blank");
		if (allBlank) {
			setShowAllBlankConfirm(true);
		} else {
			handleApprove("asset_review");
		}
	};

	const handleForceApprove = async () => {
		setShowAllBlankConfirm(false);
		try {
			await api.approveReview(job.job_id, "asset_review", true);
			load();
		} catch (e) {
			console.error("force approve failed", e);
			setError("强制审核失败");
		}
	};

	const panelProps = {
		job,
		activeStepKey,
		scriptContent,
		selectedClips,
		selectedClipsLoadState,
		rejectedClips,
		showAllBlankConfirm,
		ttsVoices,
		ttsVoiceInfo,
		ttsSelectedModel,
		ttsSelectedVoice,
		ttsPreviewUrl,
		ttsPreviewLoading,
		showVoiceConfirm,
		pendingVoiceChange,
		ttsVoiceError,
		exportTask,
		exportCreating,
		exportDownloading,
		isCurrentReviewStep,
		onApprove: handleApprove,
		onReject: handleReject,
		onRetry: handleRetry,
		onEditScript: handleEditScript,
		onRegenerateWithPrompt: handleRegenerateWithPrompt,
		onCreateExport: handleCreateExport,
		onDownloadExport: handleDownloadExport,
		onTtsModelChange: handleTtsModelChange,
		onTtsVoiceChange: handleTtsVoiceSelectChange,
		onTtsPreview: handleTtsPreview,
		onApplyVoiceChange: handleTtsVoiceChange,
		onConfirmVoiceChange: handleConfirmVoiceChange,
		onCancelVoiceChange: handleCancelVoiceChange,
		onRejectClip: handleRejectClip,
		onToggleBlank: handleToggleBlank,
		onRestoreClip: handleRestoreClip,
		onSelectAsset: handleSelectAsset,
		onAssetApprove: handleAssetApprove,
		onForceApprove: handleForceApprove,
		onDismissAllBlankConfirm: () => setShowAllBlankConfirm(false),
		findArtifact,
		getPhasePresentation,
	};

	const renderDetail = () => {
		switch (activeStepKey) {
			case "scene_assemble":
				return <SceneAssemblyPanel {...panelProps} />;
			case "draft":
				return <QueuedPanel draft={true} />;
			case "queued":
				return <QueuedPanel />;
			case "script_gen":
			case "script_review":
				return <ScriptPanel {...panelProps} />;
			case "tts":
				return <TtsPanel {...panelProps} />;
			case "tts_review":
				return <TtsReviewPanel {...panelProps} />;
			case "subtitle":
				return <SubtitlePanel {...panelProps} />;
			case "asset_retrieving":
				return <AssetRetrievingPanel {...panelProps} />;
			case "asset_review":
				return <AssetReviewPanel {...panelProps} />;
			case "montage":
				return <MontagePanel {...panelProps} />;
			case "video_base":
				return <VideoBasePanel {...panelProps} />;
			case "final_render":
				return <FinalRenderPanel {...panelProps} />;
			case "final_review":
				return <FinalReviewPanel {...panelProps} />;
			case "completed":
				return <CompletedPanel {...panelProps} />;
			case "failed":
				return <FailedPanel {...panelProps} />;
			case "cancelled":
				return <CancelledPanel />;
			case "paused":
				return <PausedPanel />;
			default:
				return (
					<div className="text-[var(--text-tertiary)] text-sm">未知步骤</div>
				);
		}
	};

	return (
		<div>
			<div className="flex items-center gap-2 mb-4">
				<button
					className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-sm"
					onClick={() => navigate(`/projects/${job.project_id}`)}
				>
					{"←"} 返回工作台
				</button>
				<span className="text-[var(--text-tertiary)]">|</span>
				<h1 className="text-lg font-bold font-mono">
					{job.name || job.job_id}
				</h1>
				{job.product && (
					<span className="text-xs text-[var(--text-tertiary)] bg-[var(--bg-table-head)] px-2 py-0.5 rounded">
						{job.product}
					</span>
				)}
			</div>

			{error && (
				<div className="mb-4 bg-[var(--alert-red-muted)] border border-[var(--danger-border)] text-[var(--alert-red)] px-4 py-3 rounded-lg text-sm flex items-center justify-between">
					<span>{error}</span>
					<button
						onClick={() => setError("")}
						className="text-[var(--text-tertiary)] hover:text-[var(--alert-red)] text-lg leading-none"
					>
						&times;
					</button>
				</div>
			)}

			{job.execution?.status === "retrying" && (
				<div className="mb-4 bg-[var(--bg-table-head)] px-4 py-3 rounded-lg text-sm">
					正在自动重试：第 {job.execution.current_attempt}{" "}
					次执行失败，系统将按退避策略继续尝试。
				</div>
			)}

			<div className="flex flex-col md:flex-row border rounded-xl min-h-[500px]">
				<PipelineSidebar
					currentPhase={job.phase}
					completedPhases={computeCompletedPhases(job.phase)}
					onStepClick={(key) => setActiveStepKey(key)}
					activeStepKey={activeStepKey}
					jobInfo={
						job.name
							? `${job.name} (${job.product})`
							: job.product
								? `${job.job_id} ${job.product}`
								: job.job_id
					}
					mode={job.mode}
					actionPolicy={getJobActionPolicy(job)}
					onPause={handlePause}
					onResume={handleResume}
					onCancel={handleCancel}
					onRetry={handleRetry}
					onViewLogs={async () => {
						try {
							const r = await api.getJobLogs(job.job_id);
							alert(r.logs || "无日志");
						} catch {
							alert("无法加载日志");
						}
					}}
				/>
				<div className="flex-1 min-w-0 p-5 bg-[var(--bg-page)] overflow-x-auto">
					{renderDetail()}
				</div>
			</div>
		</div>
	);
}
