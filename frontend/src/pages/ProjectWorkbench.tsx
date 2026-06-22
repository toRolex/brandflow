import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { JobSummary, ScheduleEntry, MusicTrack } from "../types";
import JobTable from "../components/JobTable";
import ScheduleTable from "../components/ScheduleTable";
import SmartAssetLibrary from "./SmartAssetLibrary";
import BatchScriptUploader from "../components/BatchScriptUploader";
import { applyScriptSplit, type BatchConfig, defaultBatchConfig } from "../utils/batchScriptSplit";

const PRODUCTS = ["荔枝菌", "羊肚菌", "松茸"];
const PLATFORMS = [
  { key: "douyin", label: "抖音" },
  { key: "xiaohongshu", label: "小红书" },
  { key: "shipinhao", label: "视频号" },
  { key: "kuaishou", label: "快手" },
];


export default function ProjectWorkbench() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [schedule, setSchedule] = useState<ScheduleEntry[]>([]);
  const [product, setProduct] = useState(PRODUCTS[0]);
  const [platforms, setPlatforms] = useState<string[]>(["douyin", "xiaohongshu"]);
  const [tab, setTab] = useState<"jobs" | "schedule" | "assets">("jobs");
  const [projectName, setProjectName] = useState("");
  const [error, setError] = useState("");
  const [manualScript, setManualScript] = useState("");
  const [jobName, setJobName] = useState("");
  const [scriptMode, setScriptMode] = useState<"auto" | "manual">("auto");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioMode, setAudioMode] = useState<"tts" | "upload" | "library">("tts");
  const [musicTracks, setMusicTracks] = useState<MusicTrack[]>([]);
  const [selectedMusic, setSelectedMusic] = useState("");
  const [musicVolume, setMusicVolume] = useState(80);
  const [language, setLanguage] = useState<"mandarin" | "cantonese">("mandarin");
  const [batchLanguage, setBatchLanguage] = useState(false);

  /* ── 批量创建相关状态 ── */
  const [batchMode, setBatchMode] = useState(false);
  const [batchCount, setBatchCount] = useState(2);
  const [batchConfigs, setBatchConfigs] = useState<BatchConfig[]>(() =>
    Array.from({ length: 2 }, () => defaultBatchConfig()),
  );
  const [autoApprove, setAutoApprove] = useState(false);
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [batchCreating, setBatchCreating] = useState(false);

  /* 批量数量变化时同步 batchConfigs 长度 */
  useEffect(() => {
    setBatchConfigs((prev) => {
      if (prev.length === batchCount) return prev;
      if (prev.length < batchCount) {
        const added = Array.from(
          { length: batchCount - prev.length },
          () => defaultBatchConfig(),
        );
        return [...prev, ...added];
      }
      return prev.slice(0, batchCount);
    });
  }, [batchCount]);

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
    try {
      const sched = await api.getSchedule({ project_id: id });
      setSchedule(sched);
    } catch (e) {
      console.error("load schedule failed", e);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    api.listMusic().then((data) => setMusicTracks(data.tracks)).catch(() => {});
  }, []);

  /* ── 单个创建（保持现有流程不变） ── */
  const handleCreateJob = async () => {
    if (!id) return;
    try {
      const job = await api.createJob(id, {
        product,
        platforms,
        name: jobName || undefined,
        manual_script: scriptMode === "manual" ? manualScript : "",
        audio_source: audioMode,
        language: language,
      });
      if (audioMode === "upload" && audioFile) {
        await api.uploadJobAudio(job.job_id, audioFile);
      }
      navigate(`/jobs/${job.job_id}`);
    } catch (e) {
      console.error("create job failed", e);
      setError("创建 Job 失败");
    }
  };

  /* ── 批量创建 ── */
  const handleBatchCreate = async () => {
    if (!id) return;
    setBatchCreating(true);
    try {
      await api.batchCreateJobs(id, { product, platforms, auto_approve: autoApprove, jobs: batchConfigs.map((c, i) => ({
        name: c.name || `${product} #${String(i + 1).padStart(3, "0")}`,
        manual_script: c.scriptMode === "manual" ? c.manualScript : "",
        skip_subtitle: c.skipSubtitle,
        audio_source: c.audioMode,
        language: c.language,
      })) });
      load();
    } catch (e) {
      console.error("batch create failed", e);
      setError("批量创建失败");
    } finally {
      setBatchCreating(false);
    }
  };

  function updateBatchConfig(index: number, partial: Partial<BatchConfig>) {
    setBatchConfigs((prev) =>
      prev.map((c, i) => (i === index ? { ...c, ...partial } : c)),
    );
  }

  function handleScriptsUpload(scripts: string[]) {
    setBatchConfigs((prev) => {
      const merged = applyScriptSplit(scripts, prev);
      setBatchCount(merged.length);
      return merged;
    });
  }

  const handleRetry = async (jobId: string) => {
    await api.retryJob(jobId);
    load();
  };

  const handleDeleteJob = async (jobId: string) => {
    if (!window.confirm(`确认删除 Job ${jobId}？此操作不可撤销。`)) return;
    try {
      await api.deleteJob(jobId);
      load();
    } catch (e) {
      console.error("delete job failed", e);
      setError("删除 Job 失败");
    }
  };

  const handleRenameJob = async (jobId: string, name: string) => {
    await api.renameJob(jobId, name);
  };

  const togglePlatform = (p: string) => {
    setPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p],
    );
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <button className="text-gray-500 hover:text-gray-700 text-sm" onClick={() => navigate("/")}>
          &#8592; 项目列表
        </button>
        <span className="text-gray-300">|</span>
        <h1 className="text-lg font-bold">{projectName || id}</h1>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError("")} className="text-red-400 hover:text-red-600 text-lg leading-none">&times;</button>
        </div>
      )}

      {/* ── 创建 Job ── */}
      <section className="border rounded-xl p-5 mb-6 bg-white">
        <h2 className="text-[15px] font-semibold mb-3.5">创建新 Job</h2>

        {/* ── 创建模式切换 ── */}
        <div className="flex items-center gap-4 mb-4 pb-4 border-b">
          <span className="text-xs text-[#59636e] font-medium">创建模式</span>
          <label className="flex items-center gap-1.5 text-sm cursor-pointer">
            <input
              type="radio"
              name="createMode"
              checked={!batchMode}
              onChange={() => setBatchMode(false)}
            />
            单个创建
          </label>
          <label className="flex items-center gap-1.5 text-sm cursor-pointer">
            <input
              type="radio"
              name="createMode"
              checked={batchMode}
              onChange={() => setBatchMode(true)}
            />
            批量创建
          </label>
          {batchMode && (
            <>
              <label className="flex items-center gap-1.5 text-sm cursor-pointer ml-4">
                <input
                  type="checkbox"
                  checked={autoApprove}
                  onChange={(e) => setAutoApprove(e.target.checked)}
                />
                全自动（跳过审核）
              </label>
              <label className="flex items-center gap-1.5 text-sm cursor-pointer ml-2">
                <input
                  type="checkbox"
                  checked={batchLanguage}
                  onChange={(e) => {
                    setBatchLanguage(e.target.checked);
                    const lang = e.target.checked ? "cantonese" : "mandarin";
                    setBatchConfigs((prev) =>
                      prev.map((c) => ({ ...c, language: lang as "mandarin" | "cantonese" })),
                    );
                  }}
                />
                粤语版
              </label>
            </>
          )}
        </div>

        {/* ── 共享设置：产品 + 平台 ── */}
        <div className="flex gap-4 flex-wrap items-end">
          <label className="grid gap-1.5 text-xs text-[#59636e] min-w-[200px]">
            产品选择
            <select
              className="border rounded-lg px-3 py-2 text-sm"
              value={product}
              onChange={(e) => setProduct(e.target.value)}
            >
              {PRODUCTS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
          {!batchMode && (
            <label className="grid gap-1.5 text-xs text-[#59636e] min-w-[200px]">
              任务名称（可选）
              <input
                type="text"
                className="border rounded-lg px-3 py-2 text-sm"
                placeholder="默认使用产品名"
                value={jobName}
                onChange={(e) => setJobName(e.target.value)}
              />
            </label>
          )}
          <div className="grid gap-1 text-xs text-gray-500">
            <span className="text-xs text-[#59636e]">目标平台</span>
            <div className="flex gap-3 py-2">
              {PLATFORMS.map((p) => (
                <label key={p.key} className="flex items-center gap-1 text-sm cursor-pointer">
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

        {/* ── 批量模式 UI ── */}
        {batchMode ? (
          <>
            {/* 创建数量 */}
            <div className="mt-4 pt-4 border-t">
              <label className="grid gap-1.5 text-xs text-[#59636e] w-32">
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
                />
              </label>
              <div className="flex items-end pb-1">
                <BatchScriptUploader onScripts={handleScriptsUpload} />
              </div>
            </div>

            {/* 每个 Job 的独立配置卡片 */}
            {batchConfigs.map((c, i) => (
              <div key={i} className="mt-4 pt-4 border-t">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-sm font-semibold text-[#0969da]">
                    #{String(i + 1).padStart(3, "0")}
                  </span>
                  <input
                    type="text"
                    placeholder={`${product} 任务`}
                    value={c.name}
                    onChange={(e) => updateBatchConfig(i, { name: e.target.value })}
                    className="border rounded-lg px-3 py-1.5 text-sm flex-1 max-w-xs"
                  />
                  <label className="flex items-center gap-1.5 text-sm cursor-pointer ml-4">
                    <input
                      type="checkbox"
                      checked={c.skipSubtitle}
                      onChange={(e) => updateBatchConfig(i, { skipSubtitle: e.target.checked })}
                    />
                    跳过字幕
                  </label>
                  <label className="flex items-center gap-1.5 text-sm cursor-pointer ml-2">
                    <input
                      type="checkbox"
                      checked={c.language === "cantonese"}
                      onChange={(e) =>
                        updateBatchConfig(i, { language: e.target.checked ? "cantonese" : "mandarin" })
                      }
                    />
                    粤语
                  </label>
                </div>

                {/* 文案来源 */}
                <div className="flex items-center gap-4 mb-3">
                  <span className="text-xs text-[#59636e] font-medium">文案来源</span>
                  <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name={`batchScriptMode-${i}`}
                      checked={c.scriptMode === "auto"}
                      onChange={() => updateBatchConfig(i, { scriptMode: "auto" })}
                    />
                    自动生成（LLM）
                  </label>
                  <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name={`batchScriptMode-${i}`}
                      checked={c.scriptMode === "manual"}
                      onChange={() => updateBatchConfig(i, { scriptMode: "manual" })}
                    />
                    手动输入
                  </label>
                </div>
                {c.scriptMode === "manual" && (
                  <textarea
                    className="w-full border rounded-lg px-3 py-2 text-sm min-h-[80px] mb-3 placeholder:text-gray-400"
                    placeholder="请输入文案内容（150-200字）..."
                    value={c.manualScript}
                    onChange={(e) => updateBatchConfig(i, { manualScript: e.target.value })}
                  />
                )}

                {/* 音频来源 */}
                <div className="flex items-center gap-4 mb-3">
                  <span className="text-xs text-[#59636e] font-medium">音频来源</span>
                  <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name={`batchAudioMode-${i}`}
                      checked={c.audioMode === "tts"}
                      onChange={() => updateBatchConfig(i, { audioMode: "tts" })}
                    />
                    TTS 生成
                  </label>
                  <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name={`batchAudioMode-${i}`}
                      checked={c.audioMode === "upload"}
                      onChange={() => updateBatchConfig(i, { audioMode: "upload" })}
                    />
                    上传音频
                  </label>
                  <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name={`batchAudioMode-${i}`}
                      checked={c.audioMode === "library"}
                      onChange={() => updateBatchConfig(i, { audioMode: "library" })}
                    />
                    音乐库
                  </label>
                </div>
                {c.audioMode === "upload" && (
                  <div className="flex items-center gap-3">
                    <label className="border-2 border-dashed border-gray-300 rounded-lg px-6 py-3 text-sm text-gray-500 hover:border-gray-400 cursor-pointer transition-colors">
                      <input
                        type="file"
                        accept="audio/*"
                        className="hidden"
                        onChange={(e) =>
                          updateBatchConfig(i, { audioFile: e.target.files?.[0] || null })
                        }
                      />
                      {c.audioFile ? c.audioFile.name : "点击选择音频文件"}
                    </label>
                    {c.audioFile && (
                      <span className="text-xs text-green-600">&#10003; 已选择</span>
                    )}
                  </div>
                )}
                {c.audioMode === "library" && (
                  <div className="flex items-center gap-3 flex-wrap mb-3">
                    <select
                      className="border rounded-lg px-3 py-1.5 text-sm min-w-[200px]"
                      value={c.musicPath}
                      onChange={(e) => updateBatchConfig(i, { musicPath: e.target.value })}
                    >
                      <option value="">-- 选择背景音乐 --</option>
                      {musicTracks.map((t) => (
                        <option key={t.relative_path} value={t.relative_path}>
                          {t.filename}
                          {t.duration_seconds != null
                            ? ` (${Math.floor(t.duration_seconds)}s)`
                            : ""}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="text-xs border rounded px-2 py-1.5 hover:bg-gray-50"
                      onClick={() => {
                        if (musicTracks.length === 0) return;
                        const pick = musicTracks[Math.floor(Math.random() * musicTracks.length)];
                        updateBatchConfig(i, { musicPath: pick.relative_path });
                      }}
                    >
                      🎲 随机
                    </button>
                    {musicTracks.length === 0 && (
                      <span className="text-xs text-gray-400">
                        音乐库为空，请将音频文件放入 workspace/music_library/
                      </span>
                    )}
                    <label className="flex items-center gap-2 text-xs text-[#59636e] ml-4">
                      音量
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={c.musicVolume}
                        onChange={(e) => updateBatchConfig(i, { musicVolume: Number(e.target.value) })}
                        className="w-24"
                      />
                      <span className="w-8 text-right">{c.musicVolume}%</span>
                    </label>
                  </div>
                )}
              </div>
            ))}

            {/* 批量创建按钮 */}
            <div className="mt-4 pt-4 border-t flex justify-end">
              <button
                className="bg-[#d1242f] text-white border-none px-8 py-3 rounded-lg text-[15px] font-semibold hover:brightness-110 transition-all disabled:opacity-50"
                onClick={handleBatchCreate}
                disabled={batchCreating}
              >
                {batchCreating ? "创建中…" : `批量创建 ${batchCount} 个 Job`}
              </button>
            </div>
          </>
        ) : (
          /* ── 单个创建 UI（保持现有流程不变） ── */
          <>
            {/* Script Input Section */}
            <div className="mt-4 pt-4 border-t">
              <div className="flex items-center gap-4 mb-3">
                <span className="text-xs text-[#59636e] font-medium">文案来源</span>
                <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="scriptMode"
                    checked={scriptMode === "auto"}
                    onChange={() => setScriptMode("auto")}
                  />
                  自动生成（LLM）
                </label>
                <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="scriptMode"
                    checked={scriptMode === "manual"}
                    onChange={() => setScriptMode("manual")}
                  />
                  手动输入
                </label>
                <label className="flex items-center gap-1.5 text-sm cursor-pointer ml-4">
                  <input
                    type="checkbox"
                    checked={language === "cantonese"}
                    onChange={(e) => setLanguage(e.target.checked ? "cantonese" : "mandarin")}
                  />
                  粤语版
                </label>
              </div>
              {scriptMode === "manual" && (
                <textarea
                  className="w-full border rounded-lg px-3 py-2 text-sm min-h-[120px] placeholder:text-gray-400"
                  placeholder="请输入文案内容（150-200字）..."
                  value={manualScript}
                  onChange={(e) => setManualScript(e.target.value)}
                />
              )}
            </div>

            {/* Audio Upload Section */}
            <div className="mt-4 pt-4 border-t">
              <div className="flex items-center gap-4 mb-3">
                <span className="text-xs text-[#59636e] font-medium">音频来源</span>
                <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="audioMode"
                    checked={audioMode === "tts"}
                    onChange={() => setAudioMode("tts")}
                  />
                  TTS 生成
                </label>
                <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="audioMode"
                    checked={audioMode === "upload"}
                    onChange={() => setAudioMode("upload")}
                  />
                  上传音频
                </label>
                <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="audioMode"
                    checked={audioMode === "library"}
                    onChange={() => setAudioMode("library")}
                  />
                  音乐库
                </label>
              </div>
              {audioMode === "upload" && (
                <div className="flex items-center gap-3">
                  <label className="border-2 border-dashed border-gray-300 rounded-lg px-6 py-4 text-sm text-gray-500 hover:border-gray-400 cursor-pointer transition-colors">
                    <input
                      type="file"
                      accept="audio/*"
                      className="hidden"
                      onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
                    />
                    {audioFile ? audioFile.name : "点击选择音频文件"}
                  </label>
                  {audioFile && (
                    <span className="text-xs text-green-600">&#10003; 已选择</span>
                  )}
                </div>
              )}
              {audioMode === "library" && (
                <div className="flex items-center gap-3 flex-wrap">
                  <select
                    className="border rounded-lg px-3 py-1.5 text-sm min-w-[200px]"
                    value={selectedMusic}
                    onChange={(e) => setSelectedMusic(e.target.value)}
                  >
                    <option value="">-- 选择背景音乐 --</option>
                    {musicTracks.map((t) => (
                      <option key={t.relative_path} value={t.relative_path}>
                        {t.filename}
                        {t.duration_seconds != null
                          ? ` (${Math.floor(t.duration_seconds)}s)`
                          : ""}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="text-xs border rounded px-2 py-1.5 hover:bg-gray-50"
                    onClick={() => {
                      if (musicTracks.length === 0) return;
                      const pick = musicTracks[Math.floor(Math.random() * musicTracks.length)];
                      setSelectedMusic(pick.relative_path);
                    }}
                  >
                    🎲 随机
                  </button>
                  {musicTracks.length === 0 && (
                    <span className="text-xs text-gray-400">
                      音乐库为空，请将音频文件放入 workspace/music_library/
                    </span>
                  )}
                  <label className="flex items-center gap-2 text-xs text-[#59636e] ml-4">
                    音量
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={musicVolume}
                      onChange={(e) => setMusicVolume(Number(e.target.value))}
                      className="w-24"
                    />
                    <span className="w-8 text-right">{musicVolume}%</span>
                  </label>
                </div>
              )}
            </div>

            <div className="mt-4 pt-4 border-t flex justify-end">
              <button
                className="bg-[#d1242f] text-white border-none px-8 py-3 rounded-lg text-[15px] font-semibold hover:brightness-110 transition-all"
                onClick={handleCreateJob}
              >
                创建并开始生产
              </button>
            </div>
          </>
        )}
      </section>

      {/* Tab: Jobs / Schedule */}
      <div className="flex gap-4 border-b mb-4">
        <button
          className={`pb-2 text-sm font-medium transition-colors ${
            tab === "jobs"
              ? "border-b-2 border-[#0969da] text-[#0969da]"
              : "text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("jobs")}
        >
          Job 列表
        </button>
        <button
          className={`pb-2 text-sm font-medium transition-colors ${
            tab === "schedule"
              ? "border-b-2 border-[#0969da] text-[#0969da]"
              : "text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("schedule")}
        >
          排期池
        </button>
        <button
          className={`pb-2 text-sm font-medium transition-colors ${
            tab === "assets"
              ? "border-b-2 border-[#0969da] text-[#0969da]"
              : "text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("assets")}
        >
          智能素材库
        </button>
      </div>

      {tab === "jobs" ? (
        <JobTable
          jobs={jobs}
          onRetry={handleRetry}
          onDelete={handleDeleteJob}
          onRename={handleRenameJob}
          selectedJobIds={selectedJobIds}
          onSelectionChange={setSelectedJobIds}
        />
      ) : tab === "schedule" ? (
        <ScheduleTable
          entries={schedule}
          onExport={() => api.exportSchedule()}
        />
      ) : (
        <SmartAssetLibrary projectId={id!} />
      )}
    </div>
  );
}
