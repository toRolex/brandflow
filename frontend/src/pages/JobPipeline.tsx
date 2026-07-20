import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import AssetGrid from "../components/AssetGrid";
import ClipReviewCard from "../components/ClipReviewCard";
import ExportTaskControls from "../components/ExportTaskControls";
import MediaPlayer from "../components/MediaPlayer";
import PipelineSidebar from "../components/PipelineSidebar";
import ScriptPreview from "../components/ScriptPreview";
import type { ExportTaskState, JobDetail, Phase, SceneFolder } from "../types";
import { PIPELINE_STEPS } from "../types";

const EXPORT_POLL_INTERVAL_MS = 2000;

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
	const [rejectedClips, setRejectedClips] = useState<Set<number>>(new Set());
	const [showAllBlankConfirm, setShowAllBlankConfirm] = useState(false);
	const [sceneFolders, setSceneFolders] = useState<SceneFolder[]>([]);
	const [selectedSceneFolders, setSelectedSceneFolders] = useState<string[]>(
		[],
	);
	const initialLoad = useRef(true);

	// TTS voice selection state (#177)
	const [ttsVoices, setTtsVoices] = useState<
		Array<{ id: string; label: string; note: string; model: string }>
	>([]);
	const [ttsVoiceInfo, setTtsVoiceInfo] = useState<{
		model: string;
		voice: string;
		resolved_from: string;
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

	// Export task state (#255)
	const [exportTask, setExportTask] = useState<ExportTaskState | null>(null);
	const [exportCreating, setExportCreating] = useState(false);
	const [exportDownloading, setExportDownloading] = useState(false);

	const phaseToStepKey = (phase: Phase): string => {
		const step = PIPELINE_STEPS.find((s) => s.phase === phase);
		return step ? step.key : "";
	};

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
		if (!id) return;
		const t = setInterval(load, 10_000);
		return () => clearInterval(t);
	}, [id, load]);

	// Sync activeStepKey when backend phase changes (auto_tick advances)
	const prevPhaseRef = useRef(job?.phase);
	useEffect(() => {
		if (!job) return;
		if (job.phase !== prevPhaseRef.current) {
			prevPhaseRef.current = job.phase;
			setActiveStepKey(phaseToStepKey(job.phase));
		}
	}, [job?.phase]);

	// Fetch script content when script artifact changes
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

	// Fetch selected clips when artifact changes
	useEffect(() => {
		if (!job) return;
		const clipsArtifact = job.artifacts?.find(
			(a) => a.kind === "selected_clips",
		);
		if (clipsArtifact?.url) {
			fetch(clipsArtifact.url)
				.then((r) => r.json())
				.then((data) => setSelectedClips(Array.isArray(data) ? data : []))
				.catch(() => setSelectedClips([]));
		} else {
			setSelectedClips([]);
		}
	}, [job, job?.artifacts]);

	// Fetch scene folders when migration is required
	useEffect(() => {
		if (!job || job.phase !== "migration_required") return;
		api
			.getSceneFolders(job.product)
			.then((data) => setSceneFolders(data.folders))
			.catch(() => setError("加载场景文件夹失败"));
	}, [job?.phase, job?.product]);

	// Fetch TTS voice info when on a TTS-related step (#177)
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

	// Fetch available voices when model changes (#177)
	useEffect(() => {
		if (!ttsSelectedModel) return;
		api
			.getTTSVoices(undefined, ttsSelectedModel)
			.then((data) => setTtsVoices(data.preset_voices))
			.catch(() => setTtsVoices([]));
	}, [ttsSelectedModel]);

	// Export task: restore on mount (page refresh) and poll while queued/running (#255)
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

	const isCurrentReviewStep = (() => {
		const step = PIPELINE_STEPS.find((s) => s.key === activeStepKey);
		if (!step || !step.isReview) return false;
		return job.phase === step.phase;
	})();

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

	const handleMigrateScenes = async () => {
		if (!job) return;
		try {
			await api.migrateScenes(job.job_id, selectedSceneFolders);
			setSelectedSceneFolders([]);
			await load();
		} catch (e) {
			console.error("migrate scenes failed", e);
			if (e instanceof Error) {
				setError(e.message);
			} else {
				setError("场景迁移失败");
			}
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

	// TTS voice preview handler (#177)
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

	// TTS voice change handler (#177)
	const handleTtsVoiceChange = (model?: string, voice?: string) => {
		if (!model && !voice) return;
		// Check if audio exists (has tts_audio artifact) - show confirm if so
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
			// Clear preview URL when voice changes
			if (ttsPreviewUrl) {
				URL.revokeObjectURL(ttsPreviewUrl);
				setTtsPreviewUrl("");
			}
		} catch (e: unknown) {
			if (e instanceof Error && e.message.includes("409")) {
				// Need confirmation
				setPendingVoiceChange({ model, voice });
				setShowVoiceConfirm(true);
				return;
			}
			if (e instanceof Error && e.message.includes("422")) {
				// Inline validation error — extract detail message (#252)
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
			// Reload job to pick up phase change
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

	const renderTtsVoiceSelector = () => {
		// Upload/library audio source: TTS controls not applicable (#252)
		if (job.audio_source === "upload" || job.audio_source === "library") {
			return (
				<div
					className="mb-4 p-3 rounded-lg border"
					style={{
						borderColor: "var(--border-default)",
						background: "var(--bg-table-head)",
					}}
				>
					<span className="text-xs" style={{ color: "var(--text-secondary)" }}>
						此 Job 使用已有音频，TTS 设置不生效
					</span>
				</div>
			);
		}

		const ResolvedLabels: Record<string, string> = {
			job: "Job",
			product: "产品",
			global: "全局",
		};
		const resolvedLabel = ttsVoiceInfo
			? ResolvedLabels[ttsVoiceInfo.resolved_from] || ttsVoiceInfo.resolved_from
			: "";
		const resolvedBadgeColor =
			ttsVoiceInfo?.resolved_from === "job"
				? "var(--btn-primary-bg)"
				: ttsVoiceInfo?.resolved_from === "product"
					? "var(--color-caution-amber)"
					: "var(--text-tertiary)";

		return (
			<div
				className="mb-4 p-3 rounded-lg border"
				style={{
					borderColor: "var(--border-default)",
					background: "var(--bg-table-head)",
				}}
			>
				{/* Resolution badge */}
				{ttsVoiceInfo && (
					<div className="flex items-center gap-2 mb-3">
						<span
							className="text-xs"
							style={{ color: "var(--text-secondary)" }}
						>
							当前音色:
						</span>
						<span
							className="text-xs font-mono"
							style={{ color: "var(--text-primary)" }}
						>
							{ttsVoiceInfo.model} / {ttsVoiceInfo.voice}
						</span>
						<span
							className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
							style={{ background: resolvedBadgeColor, color: "#fff" }}
						>
							{resolvedLabel}
						</span>
					</div>
				)}

				{/* Voice selector */}
				<div className="flex flex-wrap items-center gap-2 mb-2">
					<select
						className="text-xs border rounded px-2 py-1"
						style={{
							borderColor: "var(--border-default)",
							background: "var(--bg-page)",
							color: "var(--text-primary)",
						}}
						value={ttsSelectedModel}
						onChange={(e) => {
							const newModel = e.target.value;
							setTtsSelectedModel(newModel);
							setTtsSelectedVoice(""); // clear old model's voice (#252)
							setTtsVoiceError("");
							// Auto-select first valid voice for the new model
							api
								.getTTSVoices(undefined, newModel)
								.then((data) => {
									setTtsVoices(data.preset_voices);
									if (data.preset_voices.length > 0) {
										const isPresetModel =
											newModel === "mimo-v2.5-tts" ||
											newModel === "qwen3-tts-flash" ||
											newModel === "qwen3-tts-instruct-flash";
										if (isPresetModel) {
											setTtsSelectedVoice(data.preset_voices[0].id);
										}
									}
								})
								.catch(() => setTtsVoices([]));
						}}
					>
						{ttsVoiceInfo && (
							<option value={ttsVoiceInfo.model}>
								{ttsVoiceInfo.model} (当前)
							</option>
						)}
						<option value="mimo-v2.5-tts">mimo-v2.5-tts</option>
						<option value="mimo-v2.5-tts-voicedesign">
							mimo-v2.5-tts-voicedesign
						</option>
						<option value="mimo-v2.5-tts-voiceclone">
							mimo-v2.5-tts-voiceclone
						</option>
						<option value="qwen3-tts-flash">qwen3-tts-flash</option>
						<option value="qwen3-tts-instruct-flash">
							qwen3-tts-instruct-flash
						</option>
					</select>

					<select
						className="text-xs border rounded px-2 py-1 flex-1 min-w-[120px]"
						style={{
							borderColor: "var(--border-default)",
							background: "var(--bg-page)",
							color: "var(--text-primary)",
						}}
						value={ttsSelectedVoice}
						onChange={(e) => setTtsSelectedVoice(e.target.value)}
					>
						{ttsVoices.length === 0 && ttsVoiceInfo && (
							<option value={ttsVoiceInfo.voice}>
								{ttsVoiceInfo.voice} (当前)
							</option>
						)}
						{ttsVoices.map((v) => (
							<option key={v.id} value={v.id}>
								{v.label} ({v.id})
							</option>
						))}
					</select>

					<button
						className="text-xs px-3 py-1 rounded-md"
						style={{
							background: "var(--btn-primary-bg)",
							color: "var(--btn-primary-text)",
						}}
						onClick={() =>
							handleTtsVoiceChange(ttsSelectedModel, ttsSelectedVoice)
						}
					>
						应用
					</button>
				</div>

				{/* Inline validation error (#252) */}
				{ttsVoiceError && (
					<div
						className="mt-2 text-xs px-3 py-2 rounded"
						style={{
							background: "var(--alert-red-muted)",
							color: "var(--alert-red)",
							border: "1px solid var(--danger-border)",
						}}
					>
						{ttsVoiceError}
					</div>
				)}

				{/* Preview button */}
				<div className="flex items-center gap-2">
					<button
						className="text-xs px-3 py-1 rounded-md disabled:opacity-50"
						style={{
							background: "var(--bg-table-head)",
							color: "var(--text-link)",
							border: "1px solid var(--border-default)",
						}}
						onClick={handleTtsPreview}
						disabled={ttsPreviewLoading}
					>
						{ttsPreviewLoading ? "试听中..." : "试听"}
					</button>
					{ttsPreviewUrl && (
						<span
							className="text-[10px]"
							style={{ color: "var(--signal-green)" }}
						>
							试听就绪
						</span>
					)}
				</div>

				{/* Link to global TTS config */}
				<div className="mt-2">
					<a
						href="/tts-config"
						className="text-[10px] hover:underline"
						style={{ color: "var(--text-tertiary)" }}
						target="_blank"
						rel="noopener noreferrer"
					>
						高级 TTS 配置
					</a>
				</div>

				{/* Confirmation dialog */}
				{showVoiceConfirm && (
					<div
						className="mt-3 p-3 rounded-lg border"
						style={{
							borderColor: "var(--danger-border)",
							background: "var(--alert-red-muted)",
						}}
					>
						<p className="text-xs mb-2" style={{ color: "var(--alert-red)" }}>
							正式 TTS
							音频已存在，更换音色将失效下游产物（字幕、视频等），确认继续？
						</p>
						<div className="flex gap-2">
							<button
								className="text-xs px-3 py-1 rounded-md"
								style={{
									background: "var(--btn-danger-bg)",
									color: "var(--btn-danger-text)",
								}}
								onClick={handleConfirmVoiceChange}
							>
								确认更换
							</button>
							<button
								className="text-xs px-3 py-1 rounded-md"
								style={{
									background: "var(--bg-page)",
									color: "var(--text-primary)",
									border: "1px solid var(--border-default)",
								}}
								onClick={handleCancelVoiceChange}
							>
								取消
							</button>
						</div>
					</div>
				)}
			</div>
		);
	};

	const renderDetail = () => {
		switch (activeStepKey) {
			case "migration_required":
				return (
					<div className="py-4">
						<div
							className="flex items-center gap-2 mb-4 p-3 rounded-lg border"
							style={{
								borderColor: "var(--color-caution-amber)",
								background: "var(--bg-table-head)",
							}}
						>
							<span
								className="text-lg shrink-0"
								style={{ color: "var(--color-caution-amber)" }}
							>
								&#9888;
							</span>
							<div>
								<h3
									className="font-semibold text-sm"
									style={{ color: "var(--text-primary)" }}
								>
									需补充场景文件夹
								</h3>
								<p
									className="text-xs mt-0.5"
									style={{ color: "var(--text-secondary)" }}
								>
									该任务为历史创建的导入任务，缺少有效的场景输入。请从下方选择场景文件夹完成迁移，系统将重建任务并保留现有文案与配置。
								</p>
							</div>
						</div>
						<p
							className="text-xs mb-4 font-medium"
							style={{ color: "var(--text-secondary)" }}
						>
							选择要使用的场景文件夹：
						</p>
						{sceneFolders.length === 0 ? (
							<p className="text-xs" style={{ color: "var(--text-secondary)" }}>
								未配置场景文件夹 — 请先在系统设置中配置场景文件夹
							</p>
						) : (
							<div className="flex flex-wrap gap-3 mb-4">
								{sceneFolders.map((folder) => (
									<label
										key={folder.path}
										className="flex items-center gap-1.5 text-sm cursor-pointer"
										style={{ color: "var(--text-primary)" }}
									>
										<input
											type="checkbox"
											checked={selectedSceneFolders.includes(folder.path)}
											onChange={(e) => {
												if (e.target.checked) {
													setSelectedSceneFolders([
														...selectedSceneFolders,
														folder.path,
													]);
												} else {
													setSelectedSceneFolders(
														selectedSceneFolders.filter(
															(id) => id !== folder.path,
														),
													);
												}
											}}
										/>
										{folder.name}
									</label>
								))}
							</div>
						)}
						<button
							className="px-4 py-2 rounded-md text-sm disabled:opacity-50"
							style={{
								background: "var(--btn-primary-bg)",
								color: "var(--btn-primary-text)",
							}}
							disabled={selectedSceneFolders.length === 0}
							onClick={handleMigrateScenes}
						>
							补充场景并重新启动任务
						</button>
					</div>
				);
			case "queued":
				return (
					<div className="text-[var(--text-tertiary)] text-sm py-4">
						任务排队中，等待系统调度...
					</div>
				);
			case "script_gen":
			case "script_review": {
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
						onApprove={() => handleApprove("script")}
						onReject={() => handleReject("script")}
						onRegenerate={handleRetry}
						onEdit={handleEditScript}
						onRegenerateWithPrompt={handleRegenerateWithPrompt}
					/>
				);
			}
			case "tts": {
				const audio = findArtifact("tts_audio");
				const execStatus = job.execution?.status;
				const execError = job.execution?.error;
				return (
					<div>
						<h3 className="font-semibold text-sm mb-3">TTS 配音</h3>
						{renderTtsVoiceSelector()}

						{/* Execution: pending */}
						{execStatus === "pending" && (
							<div className="py-4">
								<p className="text-[var(--text-tertiary)] text-sm">
									等待开始 TTS 合成...
								</p>
							</div>
						)}

						{/* Execution: running */}
						{execStatus === "running" && (
							<div className="py-4">
								<div className="flex items-center gap-2 mb-2">
									<div
										className="w-4 h-4 border-2 rounded-full animate-spin"
										style={{
											borderColor: "var(--border-default)",
											borderTopColor: "var(--btn-primary-bg)",
										}}
									/>
									<p className="text-[var(--text-tertiary)] text-sm">
										正在合成 TTS 音频...
									</p>
								</div>
								<p className="text-[var(--text-tertiary)] text-xs">
									第 {job.execution.current_attempt} /{" "}
									{job.execution.max_attempts} 次尝试
								</p>
							</div>
						)}

						{/* Execution: retrying */}
						{execStatus === "retrying" && execError && (
							<div className="mb-4">
								<div
									className="p-3 rounded-lg border mb-3"
									style={{
										borderColor: "var(--color-caution-amber)",
										background: "var(--bg-table-head)",
									}}
								>
									<div className="flex items-center gap-2 mb-1">
										<span
											className="text-sm font-medium"
											style={{ color: "var(--color-caution-amber)" }}
										>
											正在重试
										</span>
										<span
											className="text-xs"
											style={{ color: "var(--text-tertiary)" }}
										>
											第 {job.execution.current_attempt} /{" "}
											{job.execution.max_attempts} 次
										</span>
									</div>
									<p
										className="text-xs font-mono mt-1"
										style={{ color: "var(--color-caution-amber)" }}
									>
										{execError.code}
									</p>
									<p
										className="text-xs mt-1"
										style={{ color: "var(--text-secondary)" }}
									>
										{execError.message}
									</p>
								</div>
							</div>
						)}

						{/* Execution: succeeded or no status */}
						{(!execStatus ||
							execStatus === "succeeded" ||
							execStatus === "pending") && (
							<MediaPlayer
								src={audio?.url || ttsPreviewUrl || ""}
								kind="audio"
							/>
						)}

						{/* Execution: failed */}
						{execStatus === "failed" && execError && (
							<div className="mb-4">
								<div
									className="p-3 rounded-lg border mb-3"
									style={{
										borderColor: "var(--danger-border)",
										background: "var(--alert-red-muted)",
									}}
								>
									<p
										className="text-sm font-medium mb-1"
										style={{ color: "var(--alert-red)" }}
									>
										TTS 合成失败
									</p>
									<p
										className="text-xs font-mono mt-1"
										style={{ color: "var(--alert-red)" }}
									>
										{execError.code}
									</p>
									<p
										className="text-xs mt-1"
										style={{ color: "var(--text-secondary)" }}
									>
										{execError.message}
									</p>
									{execError.retryable && (
										<p
											className="text-xs mt-1"
											style={{ color: "var(--text-tertiary)" }}
										>
											尝试次数：{job.execution.current_attempt} /{" "}
											{job.execution.max_attempts}
										</p>
									)}
									{!execError.retryable && (
										<p
											className="text-xs mt-1"
											style={{ color: "var(--color-caution-amber)" }}
										>
											此错误不可重试，请检查 TTS 配置或更换模型/音色
										</p>
									)}
								</div>
								{execError.retryable && (
									<button
										className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
										onClick={handleRetry}
									>
										重试 TTS
									</button>
								)}
							</div>
						)}
					</div>
				);
			}
			case "tts_review": {
				const audio = findArtifact("tts_audio");
				return (
					<div>
						<h3 className="font-semibold text-sm mb-3">TTS 审核</h3>
						<p className="text-[var(--text-tertiary)] text-sm mb-4">
							请试听TTS配音效果，确认无误后通过
						</p>
						{renderTtsVoiceSelector()}
						<MediaPlayer src={audio?.url || ttsPreviewUrl || ""} kind="audio" />
						{!isCurrentReviewStep && (
							<div className="text-xs mb-2" style={{ color: "var(--color-caution-amber)" }}>
								当前不在该审核阶段，无法操作
							</div>
						)}
						<div className="flex gap-2 mt-4">
							<button
								className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
								onClick={() => handleApprove("tts")}
								disabled={!isCurrentReviewStep}
								aria-disabled={!isCurrentReviewStep}
							>
								{"✓"} 通过
							</button>
							<button
								className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
								onClick={() => handleReject("tts")}
								disabled={!isCurrentReviewStep}
								aria-disabled={!isCurrentReviewStep}
							>
								{"✗"} 打回重新生成
							</button>
						</div>
					</div>
				);
			}
			case "subtitle": {
				const subtitleArtifact = findArtifact("subtitle");
				return (
					<div>
						<h3 className="font-semibold text-sm mb-3">转录字幕</h3>
						{subtitleArtifact ? (
							<div>
								<p className="text-[var(--text-tertiary)] text-sm mb-2">
									字幕文件已生成
								</p>
								<a
									href={subtitleArtifact.url}
									target="_blank"
									rel="noopener noreferrer"
									className="text-[var(--text-link)] hover:underline text-sm"
								>
									下载字幕文件 ({subtitleArtifact.kind})
								</a>
							</div>
						) : (
							<p className="text-[var(--text-tertiary)] text-sm">
								等待字幕生成...
							</p>
						)}
					</div>
				);
			}
			case "asset_retrieving": {
				const execStatus = job.execution?.status;
				const clipsArtifact = findArtifact("selected_clips");
				const assetRecords = selectedClips.map((clip, index) => {
					const category = String(clip.category || "");
					return {
						asset_id: String(clip.asset_id || `clip-${index}`),
						file_path: String(clip.file_path || ""),
						category,
						product: "",
						confidence: 1,
						duration_seconds: 0,
						status: "available" as const,
						usage_count: 0,
						source_video: "",
						tags: clip.sentence ? [String(clip.sentence)] : [],
						created_at: "",
						last_used_at: "",
					};
				});

				return (
					<div>
						<h3 className="font-semibold text-sm mb-3">素材检索</h3>

						{/* State 1: waiting to start */}
						{execStatus === "pending" && (
							<div className="py-4">
								<p className="text-[var(--text-tertiary)] text-sm">
									等待开始切配...
								</p>
							</div>
						)}

						{/* State 2: running / in progress */}
						{execStatus === "running" && (
							<div className="py-4">
								<div className="flex items-center gap-2 mb-2">
									<div
										className="w-4 h-4 border-2 rounded-full animate-spin"
										style={{
											borderColor: "var(--border-default)",
											borderTopColor: "var(--btn-primary-bg)",
										}}
									/>
									<p className="text-[var(--text-tertiary)] text-sm">
										正在切配素材...
									</p>
								</div>
								<p className="text-[var(--text-tertiary)] text-xs">
									第 {job.execution.current_attempt} /{" "}
									{job.execution.max_attempts} 次尝试
								</p>
							</div>
						)}

						{/* State 3: succeeded with results */}
						{execStatus === "succeeded" && clipsArtifact && (
							<div>
								<p className="text-[var(--text-tertiary)] text-sm mb-4">
									已检索到 {selectedClips.length} 个匹配素材
								</p>
								<div className="max-h-[500px] overflow-y-auto">
									<AssetGrid
										assets={assetRecords}
										selectedIds={new Set()}
										onToggleSelect={() => {}}
										onPreview={() => {}}
									/>
								</div>
							</div>
						)}

						{/* State 4: succeeded but no assets found */}
						{execStatus === "succeeded" && !clipsArtifact && (
							<div className="py-4">
								<div
									className="p-3 rounded-lg border mb-3"
									style={{
										borderColor: "var(--color-caution-amber)",
										background: "var(--bg-table-head)",
									}}
								>
									<p
										className="text-sm font-medium"
										style={{ color: "var(--color-caution-amber)" }}
									>
										无可用素材
									</p>
									<p
										className="text-xs mt-1"
										style={{ color: "var(--text-secondary)" }}
									>
										未找到与当前文案匹配的素材。您可以修改文案后重试，或检查素材库内容。
									</p>
								</div>
								<button
									className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
									onClick={handleRetry}
								>
									重新检索素材
								</button>
							</div>
						)}

						{/* State 5: unexpected status (edge case coverage) */}
						{!["pending", "running", "succeeded"].includes(
							execStatus || "",
						) && (
							<p className="text-[var(--text-tertiary)] text-sm">
								等待素材检索...
							</p>
						)}
					</div>
				);
			}
			case "asset_review": {
				const clipsArtifact = findArtifact("selected_clips");
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

				const handleRestore = async (clipIndex: number) => {
					try {
						await api.assetRestore(job.job_id, clipIndex, job.project_id);
						load();
					} catch (e) {
						console.error("restore clip failed", e);
						setError("恢复素材失败");
					}
				};

				const allBlank =
					selectedClips.length > 0 &&
					selectedClips.every((c) => String(c.visual_type || "") === "blank");

				const handleAssetApprove = () => {
					if (allBlank) {
						setShowAllBlankConfirm(true);
					} else {
						handleApprove("asset");
					}
				};

				const handleForceApprove = async () => {
					setShowAllBlankConfirm(false);
					try {
						await api.approveReview(job.job_id, "asset", true);
						load();
					} catch (e) {
						console.error("force approve failed", e);
						setError("强制审核失败");
					}
				};

				return (
					<div>
						<h3 className="font-semibold text-sm mb-3">素材审核</h3>
						{clipsArtifact && selectedClips.length > 0 ? (
							<div>
								<p className="text-[var(--text-tertiary)] text-sm mb-4">
									请审核检索到的 {selectedClips.length} 个素材
									{rejectedClips.size > 0 && (
										<span className="text-[var(--color-alert-red)]">
											（已打回 {rejectedClips.size} 个）
										</span>
									)}
								</p>
								<div className="max-h-[600px] overflow-y-auto overflow-x-hidden space-y-3 mb-4">
									{selectedClips.map((clip, index) => (
										<ClipReviewCard
											key={`${clip.asset_id}-${index}`}
											clip={{
												sentence: String(clip.sentence || ""),
												sentence_index:
													clip.sentence_index == null
														? undefined
														: Number(clip.sentence_index),
												category: String(clip.category || ""),
												requested_category: clip.requested_category
													? String(clip.requested_category)
													: undefined,
												file_path: String(clip.file_path || ""),
												asset_id: String(clip.asset_id || ""),
												duration_seconds: clip.duration_seconds
													? Number(clip.duration_seconds)
													: undefined,
												method: String(clip.method || ""),
												visual_type:
													(clip.visual_type as
														| "clip"
														| "blank"
														| "unresolved") || "unresolved",
											}}
											index={index}
											onReject={handleRejectClip}
											onToggleBlank={handleToggleBlank}
											onRestore={handleRestore}
											rejected={rejectedClips.has(index)}
										/>
									))}
								</div>
								{!isCurrentReviewStep && (
									<div className="text-xs mb-2" style={{ color: "var(--color-caution-amber)" }}>
										当前不在该审核阶段，无法操作
									</div>
								)}
								<div className="flex gap-2">
									<button
										className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
										onClick={handleAssetApprove}
										disabled={!isCurrentReviewStep}
										aria-disabled={!isCurrentReviewStep}
									>
										{"✓"} 全部通过
									</button>
									<button
										className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
										onClick={() => handleReject("asset")}
										disabled={!isCurrentReviewStep}
										aria-disabled={!isCurrentReviewStep}
									>
										{"✗"} 全部打回重新检索
									</button>
								</div>

								{/* All-blank confirmation dialog (#254) */}
								{showAllBlankConfirm && (
									<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
										<div className="bg-white rounded-lg shadow-xl p-6 max-w-md mx-4">
											<h4 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
												确认全留空审批
											</h4>
											<p className="text-sm text-[var(--text-secondary)] mb-4">
												所有 {selectedClips.length}{" "}
												个句子均已标记为"黑帧"（留空）。确认后每个句子位置将渲染黑帧（无画面），您仍可在正式渲染前恢复素材选择。
											</p>
											<div className="flex gap-2 justify-end">
												<button
													className="px-4 py-2 rounded-md text-xs border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-table-head)]"
													onClick={() => setShowAllBlankConfirm(false)}
												>
													取消
												</button>
												<button
													className="px-4 py-2 rounded-md text-xs bg-[var(--btn-primary-bg)] text-white hover:brightness-110"
													onClick={handleForceApprove}
												>
													确认留空 (force=true)
												</button>
											</div>
										</div>
									</div>
								)}
							</div>
						) : (
							<p className="text-[var(--text-tertiary)] text-sm">
								等待素材加载...
							</p>
						)}
					</div>
				);
			}
			case "video_base": {
				const video = findArtifact("video_base");
				return (
					<div>
						<h3 className="font-semibold text-sm mb-3">底包拼接</h3>
						<MediaPlayer src={video?.url || ""} kind="video" />
					</div>
				);
			}
			case "final_review": {
				const finalVideo = findArtifact("final_video");
				return (
					<div>
						<h3 className="font-semibold text-sm mb-3">终审 · 烧录</h3>
						<MediaPlayer src={finalVideo?.url || ""} kind="video" />
						{!isCurrentReviewStep && (
							<div className="text-xs mb-2" style={{ color: "var(--color-caution-amber)" }}>
								当前不在该审核阶段，无法操作
							</div>
						)}
						<div className="flex gap-2 mt-4">
							<button
								className="bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
								onClick={() => handleApprove("final")}
								disabled={!isCurrentReviewStep}
								aria-disabled={!isCurrentReviewStep}
							>
								{"✓"} 通过
							</button>
							<button
								className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
								onClick={() => handleReject("final")}
								disabled={!isCurrentReviewStep}
								aria-disabled={!isCurrentReviewStep}
							>
								{"✗"} 打回
							</button>
						</div>
					</div>
				);
			}
			case "completed": {
				const finalVideo = findArtifact("final_video");
				return (
					<div className="text-center py-12">
						<div className="text-[var(--color-signal-green)] text-5xl mb-4">
							{"✓"}
						</div>
						<h3 className="text-lg font-semibold text-[var(--color-signal-green)] mb-2">
							生产完成
						</h3>
						<p className="text-[var(--text-tertiary)] text-sm mb-4">
							视频已生成并排期发布
						</p>
						<MediaPlayer src={finalVideo?.url || ""} kind="video" />
						<div className="flex flex-col items-center gap-3 mt-6">
							{/* Export task UI (#255) */}
							{exportCreating && (
								<div className="text-sm text-[var(--text-tertiary)]">
									正在创建...
								</div>
							)}

							{exportTask && !exportCreating && (
								<ExportTaskControls
									task={exportTask}
									downloading={exportDownloading}
									onDownload={handleDownloadExport}
									onRecreate={handleCreateExport}
								/>
							)}

							{/* Initial state: no task, not creating */}
							{!exportTask && !exportCreating && (
								<button
									className="bg-[var(--btn-danger-bg)] text-[var(--btn-danger-text)] border-none px-6 py-2.5 rounded-lg text-sm font-semibold hover:brightness-110 transition-all flex items-center gap-2"
									onClick={handleCreateExport}
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										width="16"
										height="16"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										strokeWidth="2"
										strokeLinecap="round"
										strokeLinejoin="round"
									>
										<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
										<polyline points="7 10 12 15 17 10" />
										<line x1="12" y1="15" x2="12" y2="3" />
									</svg>
									导出
								</button>
							)}
						</div>
					</div>
				);
			}
			case "failed": {
				const executionError = job.execution?.error;
				const failedPhaseLabel = (() => {
					const step = PIPELINE_STEPS.find((s) => s.phase === job.failed_phase);
					return step?.label || job.failed_phase || "unknown";
				})();
				const isRetryable = executionError?.retryable === true;
				const isAssetFailed =
					job.failed_phase === "asset_retrieving" ||
					job.failed_phase === "asset_review";

				return (
					<div className="text-center py-12">
						<div className="text-[var(--color-alert-red)] text-5xl mb-4">
							{"✗"}
						</div>
						<h3 className="text-lg font-semibold text-[var(--color-alert-red)] mb-2">
							{isAssetFailed
								? isRetryable
									? "素材检索失败（可重试）"
									: "素材检索失败（已终止）"
								: "任务失败"}
						</h3>
						{executionError ? (
							<div className="space-y-2 text-sm text-[var(--text-tertiary)]">
								<p className="font-mono text-[var(--color-alert-red)]">
									{executionError.code}
								</p>
								<p>{executionError.message}</p>
								<p>
									失败阶段：
									<span className="font-mono">{failedPhaseLabel}</span>
								</p>
								{isRetryable ? (
									<p>
										尝试次数：{job.execution.current_attempt} /{" "}
										{job.execution.max_attempts}
									</p>
								) : (
									<p className="text-[var(--color-caution-amber)]">
										此错误不可重试，请检查配置后重建任务
									</p>
								)}
							</div>
						) : (
							<p className="text-[var(--text-tertiary)] text-sm">
								{job.last_error || "未知错误"}
							</p>
						)}
						{isRetryable && (
							<button
								className="mt-4 bg-[var(--btn-primary-bg)] text-[var(--btn-primary-text)] px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
								onClick={handleRetry}
							>
								重试失败阶段
							</button>
						)}
						{!isRetryable && isAssetFailed && (
							<button
								className="mt-4 bg-[var(--bg-table-head)] text-[var(--text-link)] border border-[var(--border-default)] px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
								onClick={() => navigate(`/projects/${job.project_id}`)}
							>
								返回工作台
							</button>
						)}
					</div>
				);
			}
			case "cancelled":
				return (
					<div className="text-center py-12">
						<div className="text-[var(--text-tertiary)] text-5xl mb-4">
							{"⊘"}
						</div>
						<h3 className="text-lg font-semibold text-[var(--text-tertiary)] mb-2">
							已取消
						</h3>
						<p className="text-[var(--text-tertiary)] text-sm">
							该任务已被人工取消
						</p>
					</div>
				);
			case "paused":
				return (
					<div className="text-center py-12">
						<div className="text-[var(--text-tag-yellow)] text-5xl mb-4">
							{"⏸"}
						</div>
						<h3 className="text-lg font-semibold text-[var(--text-tag-yellow)] mb-2">
							已暂停
						</h3>
						<p className="text-[var(--text-tertiary)] text-sm">
							任务已暂停，可点击"重试当前"继续
						</p>
					</div>
				);
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
					正在重试，第 {job.execution.current_attempt} /{" "}
					{job.execution.max_attempts} 次
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
					onPause={() => api.pauseJob(job.job_id)}
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
