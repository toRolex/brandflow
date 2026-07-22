import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import BatchCreateForm from "../components/BatchCreateForm";
import ConfirmDialog from "../components/ConfirmDialog";
import type { SingleJobFormData } from "../components/CreateJobForm";
import CreateJobForm from "../components/CreateJobForm";
import InlineBanner from "../components/InlineBanner";
import Modal from "../components/Modal";
import ProjectTabs from "../components/ProjectTabs";
import WorkbenchShell from "../components/WorkbenchShell";
import { useProducts } from "../ProductContext";
import type {
	BatchCreateResponse,
	JobSummary,
	MusicTrack,
	ProductionMode,
	ScriptTemplate,
} from "../types";
import type { BatchConfig } from "../utils/batchScriptSplit";
import type { ReviewStrategy } from "../types/core";
import { shouldPollJob } from "../policies/jobPollingPolicy";

type TabKey = "jobs";

function parseApiError(e: unknown): string {
	if (!(e instanceof Error)) return "操作失败";
	const match = e.message.match(/^\d+:\s*([\s\S]*)$/);
	if (!match) return e.message || "操作失败";
	try {
		const body = JSON.parse(match[1]);
		const detail = body?.detail;
		if (typeof detail === "string") return detail;
		if (detail?.message) {
			return detail.code ? `${detail.code}: ${detail.message}` : detail.message;
		}
		if (detail?.errors && Array.isArray(detail.errors)) {
			const first = detail.errors[0];
			if (first?.error?.message) {
				return first.error.code
					? `第 ${first.index + 1} 项「${first.item_name}」验证失败: ${first.error.message} (${first.error.code})`
					: `第 ${first.index + 1} 项「${first.item_name}」验证失败: ${first.error.message}`;
			}
		}
	} catch {}
	return "操作失败";
}

export default function ProjectWorkbench() {
	const { id } = useParams<{ id: string }>();
	const navigate = useNavigate();

	/* ── 共享状态 ── */
	const [jobs, setJobs] = useState<JobSummary[]>([]);
	const [projectName, setProjectName] = useState("");
	const [error, setError] = useState("");
	const [tab, setTab] = useState<TabKey>("jobs");
	const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
	const [musicTracks, setMusicTracks] = useState<MusicTrack[]>([]);
	const [templates, setTemplates] = useState<ScriptTemplate[]>([]);

	/* ── 产品配置 ── */
	const { activeProductConfig } = useProducts();
	const productName = activeProductConfig?.default_name ?? "";
	const productBrand = activeProductConfig?.default_brand ?? "";

	/* ── 创建表单共享状态 ── */
	const [platforms, setPlatforms] = useState<string[]>([
		"douyin",
		"xiaohongshu",
	]);
	const [jobName, setJobName] = useState("");
	const [productionMode, setProductionMode] =
		useState<ProductionMode>("generate");
	const [language, setLanguage] = useState<"mandarin" | "cantonese">(
		"mandarin",
	);
	const [skipSubtitle, setSkipSubtitle] = useState(false);
	const [manualScript, setManualScript] = useState("");
	const [audioMode, setAudioMode] = useState<"tts" | "upload">("tts");
	const [audioFile, setAudioFile] = useState<File | null>(null);
	const [selectedMusic, setSelectedMusic] = useState("");
	const [musicVolume, setMusicVolume] = useState(80);
	const [coverTitleText, setCoverTitleText] = useState("");
	const [coverHighlightWords, setCoverHighlightWords] = useState("");
	const [batchMode, setBatchMode] = useState(false);
	const [selectedTemplateId, setSelectedTemplateId] = useState("");
	const [templateVariableValues, setTemplateVariableValues] = useState<
		Record<string, string>
	>({});
	const [showTemplateSection, setShowTemplateSection] = useState(false);

	/* ── ConfirmDialog 状态 ── */
	const [confirmOpen, setConfirmOpen] = useState(false);
	const [confirmMessage, setConfirmMessage] = useState("");
	const [confirmTarget, setConfirmTarget] = useState<string>("");

	/* ── modal / banner ── */
	const [isOpen, setIsOpen] = useState(false);
	const [banner, setBanner] = useState<{
		type: "success" | "error";
		message: string;
	} | null>(null);
	const [batchSummary, setBatchSummary] = useState<BatchCreateResponse | null>(
		null,
	);

	/* ── 数据加载 ── */
	const load = useCallback(async () => {
		if (!id) return;
		try {
			const proj = await api.getProject(id);
			setJobs((proj as { jobs?: JobSummary[] }).jobs || []);
			setProjectName((proj as { name?: string }).name || id);
			setError("");
		} catch (e) {
			console.error("load project failed", e);
			setError("加载项目数据失败");
		}
	}, [id]);

	useEffect(() => {
		load();
	}, [load]);

	useEffect(() => {
		if (jobs.length === 0 || !jobs.some((job) => shouldPollJob(job.phase))) return;
		const timer = setInterval(load, 5000);
		return () => clearInterval(timer);
	}, [jobs, load]);

	useEffect(() => {
		api
			.listMusic()
			.then((data) => setMusicTracks(data.tracks))
			.catch(() => {
				setError("加载音乐库失败");
			});
		api
			.listTemplates()
			.then((data) => setTemplates(data))
			.catch(() => {
				setError("加载模板列表失败");
			});
	}, []);

	/* ── 平台切换 ── */
	const togglePlatform = (p: string) => {
		setPlatforms((prev) =>
			prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p],
		);
	};

	/* ── 模板操作 ── */
	const handleSelectTemplate = async (tmplId: string) => {
		setSelectedTemplateId(tmplId);
		if (!tmplId) return;
		try {
			const tmpl = templates.find((t) => t.id === tmplId);
			if (!tmpl) return;

			const defaultName = productName;
			const defaultBrand = productBrand;

			const values: Record<string, string> = {};
			for (const v of tmpl.variables) {
				if (v.source === "product_config") {
					const key = v.name.toLowerCase();
					if (key.includes("brand") || key.includes("品牌")) {
						values[v.name] = defaultBrand;
					} else if (
						key.includes("product") ||
						key.includes("name") ||
						key.includes("产品") ||
						key.includes("名称")
					) {
						values[v.name] = defaultName;
					} else {
						values[v.name] = defaultName;
					}
				} else if (v.source === "manual") {
					values[v.name] = "";
				}
			}
			for (const slot of tmpl.slots) {
				values[`slot_${slot.label}`] = "";
			}
			setTemplateVariableValues(values);
		} catch {
			setError("加载模板失败");
		}
	};

	/* ── 创建 Job（单） ── */
	const handleCreateJob = async (form: SingleJobFormData) => {
		if (!id) return;
		try {
			const job = await api.createJob(id, {
				platforms: form.platforms,
				name: form.name || undefined,
				mode: form.mode,
				manual_script: form.manual_script,
				audio_source: form.audio_source,
				music_track_path: form.music_track_path,
				music_volume: form.music_volume,
				language: form.language,
				skip_subtitle: form.skip_subtitle,
				cover_title: form.cover_title_text
					? {
							text: form.cover_title_text,
							highlight_words: form.cover_highlight_words
								.split(/[,，]/)
								.map((w) => w.trim())
								.filter(Boolean),
						}
					: undefined,
			});
			if (form.audio_source === "upload") {
				if (!form.audioFile) {
					throw new Error("上传音频模式需要先选择音频文件");
				}
				await api.uploadJobAudio(job.job_id, form.audioFile);
				await api.enqueueJob(job.job_id);
			}
			setIsOpen(false);
			load();
			setBanner({
				type: "success",
				message: `Job ${job.name || job.job_id} 创建成功`,
			});
		} catch (e) {
			console.error("create job failed", e);
			setError(parseApiError(e));
		}
	};

	/* ── 批量创建 ── */
	const handleBatchCreate = async (payload: {
		platforms: string[];
		reviewStrategy: ReviewStrategy;
		jobs: BatchConfig[];
	}) => {
		if (!id) return;
		try {
			const result = await api.batchCreateJobs(id, {
				platforms: payload.platforms,
				review_strategy: payload.reviewStrategy,
				jobs: payload.jobs.map((c, i) => ({
					name: c.name || `${productName} #${String(i + 1).padStart(3, "0")}`,
					mode: c.productionMode,
					manual_script: c.manualScript,
					skip_subtitle: c.skipSubtitle,
					audio_source: "tts",
					music_track_path: c.musicPath,
					music_volume: c.musicVolume,
					language: c.language,
					cover_title: c.coverTitleText.trim()
						? {
								text: c.coverTitleText.trim(),
								highlight_words: c.coverHighlightWords
									.split(/[,，]/)
									.map((w) => w.trim())
									.filter(Boolean),
							}
						: undefined,
				})),
			});
			setBatchSummary(result);
			setBanner({
				type: "success",
				message: `已创建 ${result.count} 个 Job；${result.review_strategy === "fast_output" ? "脚本与 TTS 自动审核，素材和最终成片仍需人工审核。" : "每个审核关卡都需要人工确认。"}`,
			});
			load();
		} catch (e) {
			console.error("batch create failed", e);
			setError(parseApiError(e));
		}
	};

	/* ── Job 操作 ── */
	const handleRetry = async (jobId: string) => {
		try {
			await api.retryJob(jobId);
			load();
		} catch {
			setError("重试 Job 失败");
		}
	};

	const handleDeleteJob = (jobId: string) => {
		setConfirmTarget(jobId);
		setConfirmMessage(`确认删除 Job ${jobId}？此操作不可撤销。`);
		setConfirmOpen(true);
	};

	const confirmDelete = async () => {
		try {
			await api.deleteJob(confirmTarget);
			load();
		} catch (e) {
			console.error("delete job failed", e);
			setError("删除 Job 失败");
		} finally {
			setConfirmOpen(false);
		}
	};

	const handleRenameJob = async (jobId: string, name: string) => {
		try {
			await api.renameJob(jobId, name);
		} catch {
			setError("重命名 Job 失败");
		}
	};

	return (
		<WorkbenchShell
			projectName={projectName}
			projectId={id!}
			error={error}
			onDismissError={() => setError("")}
			onBack={() => navigate("/")}
		>
			{/* ── Banner ── */}
			{banner && (
				<InlineBanner
					type={banner.type}
					message={banner.message}
					onClose={() => setBanner(null)}
				/>
			)}
			{batchSummary && (
				<section className="mb-4 rounded-lg border p-4 text-sm" style={{ borderColor: "var(--border-default)" }}>
					<div className="font-semibold mb-2">本批创建结果：{batchSummary.count} 个 Job</div>
					<div className="text-xs mb-2" style={{ color: "var(--text-secondary)" }}>
						{batchSummary.review_strategy === "fast_output"
							? "脚本与 TTS 自动通过；将在素材审核和最终审核停留。"
							: "每个适用审核关卡都会停留，等待人工确认。"}
					</div>
					<ul className="space-y-1">
						{batchSummary.results.map((job) => (
							<li key={job.job_id}>
								<button className="text-[var(--text-link)] hover:underline" onClick={() => navigate(`/jobs/${job.job_id}`)}>
									{job.display_index} · {job.name}（{job.mode === "import" ? "导入" : "智能生成"}）
								</button>
							</li>
						))}
					</ul>
				</section>
			)}

			{/* ── Header ── */}
			<div className="flex items-center justify-between mb-6">
				<h1
					className="text-xl font-bold"
					style={{ color: "var(--text-primary)" }}
				>
					Jobs
				</h1>
				<button
					className="px-4 py-2 rounded-lg text-sm font-semibold transition-all"
					style={{
						background: "var(--btn-primary-bg)",
						color: "var(--btn-primary-text)",
					}}
					onMouseEnter={(e) => {
						e.currentTarget.style.background = "var(--btn-primary-hover)";
					}}
					onMouseLeave={(e) => {
						e.currentTarget.style.background = "var(--btn-primary-bg)";
					}}
					onClick={() => setIsOpen(true)}
				>
					＋ 新建 Job
				</button>
			</div>

			{/* ── 创建 Job Modal ── */}
			<Modal
				isOpen={isOpen}
				title="创建新 Job"
				onClose={() => setIsOpen(false)}
				size="wide"
			>
				{/* 创建模式切换 */}
				<div
					className="flex items-center gap-4 mb-4 pb-4 border-b"
					style={{ borderColor: "var(--border-default)" }}
				>
					<span
						className="text-xs font-medium"
						style={{ color: "var(--text-secondary)" }}
					>
						创建模式
					</span>
					<label
						className="flex items-center gap-1.5 text-sm cursor-pointer"
						style={{ color: "var(--text-primary)" }}
					>
						<input
							type="radio"
							name="createMode"
							checked={!batchMode}
							onChange={() => setBatchMode(false)}
						/>
						单个创建
					</label>
					<label
						className="flex items-center gap-1.5 text-sm cursor-pointer"
						style={{ color: "var(--text-primary)" }}
					>
						<input
							type="radio"
							name="createMode"
							checked={batchMode}
							onChange={() => setBatchMode(true)}
						/>
						批量创建
					</label>
				</div>

				{batchMode ? (
					<BatchCreateForm
						productName={productName}
						platforms={platforms}
						togglePlatform={togglePlatform}
						musicTracks={musicTracks}
						onBatchCreate={handleBatchCreate}
						onError={setError}
					/>
				) : (
					<CreateJobForm
						productName={productName}
						platforms={platforms}
						togglePlatform={togglePlatform}
						jobName={jobName}
						setJobName={setJobName}
						productionMode={productionMode}
						setProductionMode={setProductionMode}
						language={language}
						setLanguage={setLanguage}
						skipSubtitle={skipSubtitle}
						setSkipSubtitle={setSkipSubtitle}
						manualScript={manualScript}
						setManualScript={setManualScript}
						audioMode={audioMode}
						setAudioMode={setAudioMode}
						audioFile={audioFile}
						setAudioFile={setAudioFile}
						musicTracks={musicTracks}
						selectedMusic={selectedMusic}
						setSelectedMusic={setSelectedMusic}
						musicVolume={musicVolume}
						setMusicVolume={setMusicVolume}
						coverTitleText={coverTitleText}
						setCoverTitleText={setCoverTitleText}
						coverHighlightWords={coverHighlightWords}
						setCoverHighlightWords={setCoverHighlightWords}
						templates={templates}
						selectedTemplateId={selectedTemplateId}
						setSelectedTemplateId={setSelectedTemplateId}
						templateVariableValues={templateVariableValues}
						setTemplateVariableValues={setTemplateVariableValues}
						showTemplateSection={showTemplateSection}
						setShowTemplateSection={setShowTemplateSection}
						handleSelectTemplate={handleSelectTemplate}
						onCreateJob={handleCreateJob}
						onError={setError}
					/>
				)}
			</Modal>

			{/* ── Tabs ── */}
			<ProjectTabs
				tab={tab}
				onTabChange={setTab}
				jobs={jobs}
				selectedJobIds={selectedJobIds}
				onSelectionChange={setSelectedJobIds}
				onRetry={handleRetry}
				onDeleteJob={handleDeleteJob}
				onRenameJob={handleRenameJob}
			/>

			{/* ── ConfirmDialog ── */}
			<ConfirmDialog
				isOpen={confirmOpen}
				title="确认删除"
				message={confirmMessage}
				confirmLabel="删除"
				danger={true}
				onConfirm={confirmDelete}
				onCancel={() => setConfirmOpen(false)}
			/>
		</WorkbenchShell>
	);
}
