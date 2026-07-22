import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ApiError } from "../api/core";
import { PLATFORMS } from "../constants/platforms";
import type { MusicTrack } from "../types";
import type { ReviewStrategy } from "../types/core";
import {
	type BatchConfig,
	defaultBatchConfig,
} from "../utils/batchScriptSplit";
import BatchScriptUploader from "./BatchScriptUploader";

interface BatchCreateFormProps {
	productName: string;
	platforms: string[];
	togglePlatform: (p: string) => void;
	musicTracks: MusicTrack[];
	onBatchCreate: (payload: {
		platforms: string[];
		reviewStrategy: ReviewStrategy;
		jobs: BatchConfig[];
	}) => Promise<void>;
	onError: (msg: string) => void;
}

export default function BatchCreateForm(props: BatchCreateFormProps) {
	const {
		productName,
		platforms,
		togglePlatform,
		musicTracks,
		onBatchCreate,
		onError,
	} = props;

	const [batchCount, setBatchCount] = useState(2);
	const [batchConfigs, setBatchConfigs] = useState<BatchConfig[]>(() =>
		Array.from({ length: 2 }, () => defaultBatchConfig()),
	);
	const [reviewStrategy, setReviewStrategy] =
		useState<ReviewStrategy>("review_each");
	const [batchLanguage, setBatchLanguage] = useState(false);
	const [batchSkipSubtitle, setBatchSkipSubtitle] = useState(false);
	const [batchCreating, setBatchCreating] = useState(false);

	useEffect(() => {
		setBatchConfigs((prev) => {
			if (prev.length === batchCount) return prev;
			if (prev.length < batchCount) {
				const added = Array.from({ length: batchCount - prev.length }, () =>
					defaultBatchConfig(),
				);
				return [...prev, ...added];
			}
			return prev.slice(0, batchCount);
		});
	}, [batchCount]);

	function updateBatchConfig(index: number, partial: Partial<BatchConfig>) {
		setBatchConfigs((prev) =>
			prev.map((c, i) => (i === index ? { ...c, ...partial } : c)),
		);
	}

	function handleScriptsUpload(scripts: string[]) {
		setBatchConfigs((prev) => {
			const merged = scripts.map((script, i) => ({
				...(prev[i] ?? defaultBatchConfig()),
				scriptMode: "manual" as const,
				manualScript: script,
			}));
			setBatchCount(merged.length);
			return merged;
		});
	}

	const handleSubmit = async () => {
		setBatchCreating(true);
		try {
			await onBatchCreate({
				platforms,
			reviewStrategy,
				jobs: batchConfigs,
			});
		} finally {
			setBatchCreating(false);
		}
	};

	return (
		<>
			{/* shared fields: platforms */}
			<div className="flex gap-4 flex-wrap items-end">
				<div
					className="grid gap-1 text-xs"
					style={{ color: "var(--text-secondary)" }}
				>
					<span>目标平台</span>
					<div className="flex gap-3 py-2">
						{PLATFORMS.map((p) => (
							<label
								key={p.key}
								className="flex items-center gap-1 text-sm cursor-pointer"
								style={{ color: "var(--text-primary)" }}
							>
								<input
									type="checkbox"
									checked={platforms.includes(p.key)}
									onChange={() => togglePlatform(p.key)}
								/>
								{p.label}
							</label>
						))}
					</div>
				</div>
			</div>

			{/* batch count + uploader */}
			<div
				className="mt-4 pt-4 border-t flex items-end gap-4 flex-wrap"
				style={{ borderColor: "var(--border-default)" }}
			>
				<label
					className="grid gap-1.5 text-xs w-32"
					style={{ color: "var(--text-secondary)" }}
				>
					创建数量
					<input
						type="number"
						min={2}
						max={20}
						value={batchCount}
						onChange={(e) => {
							const v = Math.max(2, Math.min(20, Number(e.target.value) || 2));
							setBatchCount(v);
						}}
						className="border rounded-lg px-3 py-2 text-sm"
						style={{
							background: "var(--bg-input)",
							borderColor: "var(--border-default)",
							color: "var(--text-primary)",
						}}
					/>
				</label>
				<div className="flex items-end pb-1">
					<BatchScriptUploader onScripts={handleScriptsUpload} />
				</div>
			</div>

			{/* batch job cards */}
			{batchConfigs.map((c, i) => (
				<BatchJobCard
					key={i}
					index={i}
					config={c}
					updateConfig={(partial) => updateBatchConfig(i, partial)}
					productName={productName}
					musicTracks={musicTracks}
					onError={onError}
				/>
			))}

			{/* batch global toggles */}
			<div className="mt-4 flex flex-wrap items-center gap-4">
				<label
					className="flex items-center gap-1.5 text-sm cursor-pointer"
					style={{ color: "var(--text-primary)" }}
				>
					<input
						type="checkbox"
						checked={reviewStrategy === "fast_output"}
						onChange={(e) =>
							setReviewStrategy(e.target.checked ? "fast_output" : "review_each")
						}
					/>
					快速产出（仅自动通过脚本与 TTS 审核）
				</label>
				<label
					className="flex items-center gap-1.5 text-sm cursor-pointer"
					style={{ color: "var(--text-primary)" }}
				>
					<input
						type="checkbox"
						checked={batchLanguage}
						onChange={(e) => {
							setBatchLanguage(e.target.checked);
							const lang = e.target.checked ? "cantonese" : "mandarin";
							setBatchConfigs((prev) =>
								prev.map((c) => ({
									...c,
									language: lang as "mandarin" | "cantonese",
								})),
							);
						}}
					/>
					粤语版
				</label>
				<label
					className="flex items-center gap-1.5 text-sm cursor-pointer"
					style={{ color: "var(--text-primary)" }}
				>
					<input
						type="checkbox"
						checked={batchSkipSubtitle}
						onChange={(e) => {
							setBatchSkipSubtitle(e.target.checked);
							setBatchConfigs((prev) =>
								prev.map((c) => ({ ...c, skipSubtitle: e.target.checked })),
							);
						}}
					/>
					全部跳过字幕
				</label>
			</div>

			{/* batch create button */}
			<div
				className="mt-4 pt-4 border-t flex justify-end"
				style={{ borderColor: "var(--border-default)" }}
			>
				<button
					className="px-8 py-3 rounded-lg text-[15px] font-semibold disabled:opacity-50"
					style={{
						background: "var(--btn-primary-bg)",
						color: "var(--btn-primary-text)",
					}}
					onClick={handleSubmit}
					disabled={batchCreating}
				>
					{batchCreating ? "创建中…" : `批量创建 ${batchCount} 个 Job`}
				</button>
			</div>
		</>
	);
}

/* ─── BatchJobCard ─── */

interface BatchJobCardProps {
	index: number;
	config: BatchConfig;
	updateConfig: (partial: Partial<BatchConfig>) => void;
	productName: string;
	musicTracks: MusicTrack[];
	onError: (msg: string) => void;
}

function BatchJobCard({
	index,
	config,
	updateConfig,
	productName,
	musicTracks,
	onError,
}: BatchJobCardProps) {
	const [showAdvanced, setShowAdvanced] = useState(false);
	const [coverGenerating, setCoverGenerating] = useState(false);
	const [coverRetryAfter, setCoverRetryAfter] = useState(0);
	const isImport = config.productionMode === "import";
	const showScriptInput = config.scriptMode === "manual";
	const hasManualScript = config.manualScript.trim().length > 0;
	const coverBtnDisabled =
		!hasManualScript || coverGenerating || coverRetryAfter > 0;
	const coverBtnTitle = !hasManualScript
		? "输入或生成文案后可生成标题"
		: coverGenerating
			? "正在生成标题…"
			: coverRetryAfter > 0
				? `服务限流，请在 ${coverRetryAfter} 秒后重试`
				: "";

	useEffect(() => {
		if (coverRetryAfter <= 0) return;
		const timer = window.setInterval(() => {
			setCoverRetryAfter((seconds) => Math.max(0, seconds - 1));
		}, 1000);
		return () => window.clearInterval(timer);
	}, [coverRetryAfter]);

	const handleGenerateCoverTitle = async () => {
		if (coverBtnDisabled) return;
		const text = config.manualScript;
		if (!text.trim()) return;
		setCoverGenerating(true);
		try {
			const res = await api.generateCoverTitle({
				script_text: text,
				product: productName,
			});
			updateConfig({
				coverTitleText: res.text,
				coverHighlightWords: res.highlight_words.join("，"),
			});
		} catch (error) {
			if (error instanceof ApiError && error.status === 429) {
				setCoverRetryAfter(error.retryAfterSeconds ?? 1);
			} else {
				onError("生成封面标题失败，请稍后重试");
			}
		} finally {
			setCoverGenerating(false);
		}
	};

	return (
		<div
			className="mt-4 pt-4 border-t"
			style={{ borderColor: "var(--border-default)" }}
		>
			{/* header */}
			<div className="mb-3 flex flex-wrap items-center gap-2">
				<span
					className="text-sm font-semibold"
					style={{ color: "var(--accent)" }}
				>
					#{String(index + 1).padStart(3, "0")}
				</span>
				<input
					type="text"
					placeholder={`${productName} 任务`}
					value={config.name}
					onChange={(e) => updateConfig({ name: e.target.value })}
					className="min-w-0 w-full border rounded-lg px-3 py-1.5 text-sm sm:w-auto sm:flex-1 sm:max-w-xs"
					style={{
						background: "var(--bg-input)",
						borderColor: "var(--border-default)",
						color: "var(--text-primary)",
					}}
				/>
				<label
					className="flex items-center gap-1.5 text-sm cursor-pointer sm:ml-4"
					style={{ color: "var(--text-primary)" }}
				>
					<input
						type="checkbox"
						checked={config.skipSubtitle}
						onChange={(e) => updateConfig({ skipSubtitle: e.target.checked })}
					/>
					跳过字幕
				</label>
				<label
					className="flex items-center gap-1.5 text-sm cursor-pointer sm:ml-2"
					style={{ color: "var(--text-primary)" }}
				>
					<input
						type="checkbox"
						checked={config.language === "cantonese"}
						onChange={(e) =>
							updateConfig({
								language: e.target.checked ? "cantonese" : "mandarin",
							})
						}
					/>
					粤语
				</label>
			</div>

			{/* production mode */}
			<div className="mb-3 flex flex-wrap items-center gap-4">
				<span
					className="text-xs font-medium"
					style={{ color: "var(--text-secondary)" }}
				>
					生产模式
				</span>
				<div
					className="flex rounded-lg border overflow-hidden"
					style={{ borderColor: "var(--border-default)" }}
				>
					<button
						type="button"
						className="px-3 py-1 text-sm font-medium"
						style={
							config.productionMode === "generate"
								? {
										background: "var(--btn-primary-bg)",
										color: "var(--btn-primary-text)",
									}
								: {
										background: "var(--bg-card)",
										color: "var(--text-secondary)",
									}
						}
						onClick={() => updateConfig({ productionMode: "generate" })}
					>
						智能生成
					</button>
					<button
						type="button"
						className="px-3 py-1 text-sm font-medium"
						style={
							config.productionMode === "import"
								? {
										background: "var(--btn-primary-bg)",
										color: "var(--btn-primary-text)",
									}
								: {
										background: "var(--bg-card)",
										color: "var(--text-secondary)",
									}
						}
						onClick={() => updateConfig({ productionMode: "import" })}
					>
						手动导入
					</button>
				</div>
			</div>

			{/* Script textarea for manual mode (works in both generate and import) */}
			{showScriptInput && (
				<textarea
					className="w-full border rounded-lg px-3 py-2 text-sm min-h-[80px] mb-3"
					style={{
						borderColor: "var(--border-default)",
						background: "var(--bg-input)",
						color: "var(--text-primary)",
					}}
					placeholder="请输入文案内容（150-200字）..."
					value={config.manualScript}
					onChange={(e) => updateConfig({ manualScript: e.target.value })}
				/>
			)}

			{/* progressive disclosure toggle */}
			{isImport && (
				<div className="mb-3">
					<button
						type="button"
						className="text-xs font-medium flex items-center gap-1"
						style={{ color: "var(--text-secondary)" }}
						onClick={() => setShowAdvanced(!showAdvanced)}
					>
						<span
							style={{
								display: "inline-block",
								transform: showAdvanced ? "rotate(90deg)" : "rotate(0deg)",
								transition:
									"transform var(--transition-duration) var(--transition-easing)",
							}}
						>
							&#9654;
						</span>
						更多设置
					</button>
				</div>
			)}

			{/* advanced section */}
			<div
				style={{
					overflow: "hidden",
					maxHeight: !isImport || showAdvanced ? "2000px" : "0px",
					opacity: !isImport || showAdvanced ? 1 : 0,
					transition:
						"max-height var(--transition-duration) var(--transition-easing), opacity var(--transition-duration) var(--transition-easing)",
				}}
			>
				{/* Audio Source */}
				<div className="mb-3 flex flex-wrap items-center gap-4">
					<span
						className="text-xs font-medium"
						style={{ color: "var(--text-secondary)" }}
					>
						音频来源
					</span>
					<span className="text-sm" style={{ color: "var(--text-primary)" }}>
						TTS 生成
					</span>
				</div>

				{/* Cover Title */}
				<div className="mb-3 mt-3 flex flex-wrap items-center gap-4">
					<span
						className="text-xs font-medium"
						style={{ color: "var(--text-secondary)" }}
					>
						封面标题（可选）
					</span>
					<button
						type="button"
						className="text-xs border rounded px-2 py-1.5 disabled:opacity-50"
						style={{
							color: "var(--text-secondary)",
							borderColor: "var(--border-default)",
						}}
						disabled={coverBtnDisabled}
						title={coverBtnTitle}
						onClick={handleGenerateCoverTitle}
					>
						{coverGenerating
							? "正在生成标题…"
							: coverRetryAfter > 0
								? `${coverRetryAfter} 秒后重试`
								: "自动生成标题"}
					</button>
				</div>
				<div className="flex items-center gap-3 flex-wrap mb-3">
					<input
						type="text"
						className="w-full border rounded-lg px-3 py-2 text-sm sm:w-auto sm:min-w-[220px] sm:flex-1 sm:max-w-xs"
						style={{
							borderColor: "var(--border-default)",
							background: "var(--bg-input)",
							color: "var(--text-primary)",
						}}
						placeholder="输入封面标题（留空则不显示）"
						value={config.coverTitleText}
						onChange={(e) => updateConfig({ coverTitleText: e.target.value })}
					/>
					<input
						type="text"
						className="w-full border rounded-lg px-3 py-2 text-sm sm:w-auto sm:min-w-[180px]"
						style={{
							borderColor: "var(--border-default)",
							background: "var(--bg-input)",
							color: "var(--text-primary)",
						}}
						placeholder="高亮关键词，用逗号分隔"
						value={config.coverHighlightWords}
						onChange={(e) =>
							updateConfig({ coverHighlightWords: e.target.value })
						}
					/>
				</div>

				{/* Background Music */}
				<div className="mb-3 mt-3 flex flex-wrap items-center gap-4">
					<span
						className="text-xs font-medium"
						style={{ color: "var(--text-secondary)" }}
					>
						背景音乐（可选）
					</span>
				</div>
				<div className="flex items-center gap-3 flex-wrap mb-3">
					<select
						className="w-full border rounded-lg px-3 py-1.5 text-sm sm:w-auto sm:min-w-[200px]"
						style={{
							borderColor: "var(--border-default)",
							background: "var(--bg-input)",
							color: "var(--text-primary)",
						}}
						value={config.musicPath}
						onChange={(e) => updateConfig({ musicPath: e.target.value })}
					>
						<option value="">-- 选择背景音乐 --</option>
						{musicTracks.map((t) => (
							<option key={t.relative_path} value={t.relative_path}>
								{t.filename}
								{t.duration_seconds == null
									? ""
									: ` (${Math.floor(t.duration_seconds)}s)`}
							</option>
						))}
					</select>
					<button
						type="button"
						className="text-xs border rounded px-2 py-1.5"
						style={{
							color: "var(--text-secondary)",
							borderColor: "var(--border-default)",
						}}
						onClick={() => {
							if (musicTracks.length === 0) return;
							const pick =
								musicTracks[Math.floor(Math.random() * musicTracks.length)];
							updateConfig({ musicPath: pick.relative_path });
						}}
					>
						🎲 随机
					</button>
					{musicTracks.length === 0 && (
						<span
							className="text-xs"
							style={{ color: "var(--text-secondary)" }}
						>
							音乐库为空，请将音频文件放入 workspace/music_library/
						</span>
					)}
					<label
						className="flex items-center gap-2 text-xs sm:ml-4"
						style={{ color: "var(--text-secondary)" }}
					>
						音量
						<input
							type="range"
							min={0}
							max={100}
							value={config.musicVolume}
							onChange={(e) =>
								updateConfig({ musicVolume: Number(e.target.value) })
							}
							className="w-24"
						/>
						<span className="w-8 text-right">{config.musicVolume}%</span>
					</label>
				</div>
			</div>
		</div>
	);
}
