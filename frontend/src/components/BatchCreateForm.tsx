import { useState, useEffect } from "react";
import type { MusicTrack } from "../types";
import { api } from "../api/client";
import { type BatchConfig, defaultBatchConfig } from "../utils/batchScriptSplit";
import BatchScriptUploader from "./BatchScriptUploader";
import { PLATFORMS } from "../constants/platforms";

interface BatchCreateFormProps {
  product: string;
  setProduct: (v: string) => void;
  brand: string;
  setBrand: (v: string) => void;
  platforms: string[];
  togglePlatform: (p: string) => void;
  musicTracks: MusicTrack[];
  onBatchCreate: (payload: {
    product: string;
    brand?: string;
    platforms: string[];
    autoApprove: boolean;
    jobs: BatchConfig[];
  }) => Promise<void>;
  onError: (msg: string) => void;
}

export default function BatchCreateForm(props: BatchCreateFormProps) {
  const {
    product, setProduct, brand, setBrand, platforms, togglePlatform,
    musicTracks, onBatchCreate, onError,
  } = props;

  const [batchCount, setBatchCount] = useState(2);
  const [batchConfigs, setBatchConfigs] = useState<BatchConfig[]>(() =>
    Array.from({ length: 2 }, () => defaultBatchConfig()),
  );
  const [autoApprove, setAutoApprove] = useState(false);
  const [batchLanguage, setBatchLanguage] = useState(false);
  const [batchSkipSubtitle, setBatchSkipSubtitle] = useState(false);
  const [batchCreating, setBatchCreating] = useState(false);
  const [batchCoverCooldown, setBatchCoverCooldown] = useState<Set<number>>(new Set());
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
        product,
        brand: brand || undefined,
        platforms,
        autoApprove,
        jobs: batchConfigs,
      });
    } finally {
      setBatchCreating(false);
    }
  };

  return (
    <>
      {/* shared fields */}
      <div className="flex gap-4 flex-wrap items-end">
        <label className="grid gap-1.5 text-xs min-w-[200px]" style={{ color: "var(--text-secondary)" }}>
          产品名称
          <input
            type="text"
            className="border rounded-lg px-3 py-2 text-sm"
            style={{ background: "var(--bg-input)", borderColor: "var(--border-default)", color: "var(--text-primary)" }}
            placeholder="如：龙井茶"
            value={product}
            onChange={(e) => setProduct(e.target.value)}
          />
        </label>
        <label className="grid gap-1.5 text-xs min-w-[160px]" style={{ color: "var(--text-secondary)" }}>
          品牌（可选）
          <input
            type="text"
            className="border rounded-lg px-3 py-2 text-sm"
            style={{ background: "var(--bg-input)", borderColor: "var(--border-default)", color: "var(--text-primary)" }}
            placeholder="如：您的品牌名"
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
          />
        </label>
        <div className="grid gap-1 text-xs" style={{ color: "var(--text-secondary)" }}>
          <span>目标平台</span>
          <div className="flex gap-3 py-2">
            {PLATFORMS.map((p) => (
              <label key={p.key} className="flex items-center gap-1 text-sm cursor-pointer" style={{ color: "var(--text-primary)" }}>
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
      <div className="mt-4 pt-4 border-t flex items-end gap-4 flex-wrap" style={{ borderColor: "var(--border-default)" }}>
        <label className="grid gap-1.5 text-xs w-32" style={{ color: "var(--text-secondary)" }}>
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
            style={{ background: "var(--bg-input)", borderColor: "var(--border-default)", color: "var(--text-primary)" }}
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
          productName={product}
          musicTracks={musicTracks}
          coverCooldown={batchCoverCooldown.has(i)}
          setCoverCooldown={(v) => {
            setBatchCoverCooldown((prev) => {
              const next = new Set(prev);
              if (v) next.add(i); else next.delete(i);
              return next;
            });
          }}
          onError={onError}
        />
      ))}

      {/* batch global toggles */}
      <div className="mt-4 flex items-center gap-4">
        <label className="flex items-center gap-1.5 text-sm cursor-pointer" style={{ color: "var(--text-primary)" }}>
          <input
            type="checkbox"
            checked={autoApprove}
            onChange={(e) => setAutoApprove(e.target.checked)}
          />
          全自动（跳过审核）
        </label>
        <label className="flex items-center gap-1.5 text-sm cursor-pointer" style={{ color: "var(--text-primary)" }}>
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
        <label className="flex items-center gap-1.5 text-sm cursor-pointer" style={{ color: "var(--text-primary)" }}>
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
      <div className="mt-4 pt-4 border-t flex justify-end" style={{ borderColor: "var(--border-default)" }}>
        <button
          className="px-8 py-3 rounded-lg text-[15px] font-semibold disabled:opacity-50"
          style={{ background: "var(--btn-primary-bg)", color: "var(--btn-primary-text)" }}
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
  coverCooldown: boolean;
  setCoverCooldown: (v: boolean) => void;
  onError: (msg: string) => void;
}

function BatchJobCard({
  index,
  config,
  updateConfig,
  productName,
  musicTracks,
  coverCooldown,
  setCoverCooldown,
  onError,
}: BatchJobCardProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const isImport = config.productionMode === "import";
  const coverBtnDisabled = config.productionMode === "generate" || coverCooldown;
  const coverBtnTitle = coverCooldown
    ? "冷却中，请等待 5 秒"
    : config.productionMode === "generate"
      ? "智能生成模式下由 LLM 自动生成封面标题，无需手动生成"
      : "";

  const handleGenerateCoverTitle = async () => {
    if (coverCooldown) return;
    const text = isImport ? config.manualScript : "";
    if (!text.trim()) return;
    setCoverCooldown(true);
    try {
      const res = await api.generateCoverTitle({ script_text: text, product: productName });
      updateConfig({ coverTitleText: res.text, coverHighlightWords: res.highlight_words.join("，") });
    } catch {
      onError("生成封面标题失败，请稍后重试");
    } finally {
      setTimeout(() => setCoverCooldown(false), 5000);
    }
  };

  return (
    <div className="mt-4 pt-4 border-t" style={{ borderColor: "var(--border-default)" }}>
      {/* header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-semibold" style={{ color: "var(--accent)" }}>
          #{String(index + 1).padStart(3, "0")}
        </span>
        <input
          type="text"
          placeholder={`${productName} 任务`}
          value={config.name}
          onChange={(e) => updateConfig({ name: e.target.value })}
          className="border rounded-lg px-3 py-1.5 text-sm flex-1 max-w-xs"
          style={{ background: "var(--bg-input)", borderColor: "var(--border-default)", color: "var(--text-primary)" }}
        />
        <label className="flex items-center gap-1.5 text-sm cursor-pointer ml-4" style={{ color: "var(--text-primary)" }}>
          <input
            type="checkbox"
            checked={config.skipSubtitle}
            onChange={(e) => updateConfig({ skipSubtitle: e.target.checked })}
          />
          跳过字幕
        </label>
        <label className="flex items-center gap-1.5 text-sm cursor-pointer ml-2" style={{ color: "var(--text-primary)" }}>
          <input
            type="checkbox"
            checked={config.language === "cantonese"}
            onChange={(e) =>
              updateConfig({ language: e.target.checked ? "cantonese" : "mandarin" })
            }
          />
          粤语
        </label>
      </div>

      {/* production mode */}
      <div className="flex items-center gap-4 mb-3">
        <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>生产模式</span>
        <div className="flex rounded-lg border overflow-hidden" style={{ borderColor: "var(--border-default)" }}>
          <button
            type="button"
            className="px-3 py-1 text-sm font-medium"
            style={
              config.productionMode === "generate"
                ? { background: "var(--btn-primary-bg)", color: "var(--btn-primary-text)" }
                : { background: "var(--bg-card)", color: "var(--text-secondary)" }
            }
            onClick={() => updateConfig({ productionMode: "generate", scriptMode: "auto" })}
          >
            智能生成
          </button>
          <button
            type="button"
            className="px-3 py-1 text-sm font-medium"
            style={
              config.productionMode === "import"
                ? { background: "var(--btn-primary-bg)", color: "var(--btn-primary-text)" }
                : { background: "var(--bg-card)", color: "var(--text-secondary)" }
            }
            onClick={() => updateConfig({ productionMode: "import", scriptMode: "manual" })}
          >
            手动导入
          </button>
        </div>
      </div>

      {/* Import: script textarea */}
      {isImport && (
        <textarea
          className="w-full border rounded-lg px-3 py-2 text-sm min-h-[80px] mb-3"
          style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
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
            <span style={{
              display: "inline-block",
              transform: showAdvanced ? "rotate(90deg)" : "rotate(0deg)",
              transition: "transform var(--transition-duration) var(--transition-easing)",
            }}>
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
          maxHeight: (!isImport || showAdvanced) ? "2000px" : "0px",
          opacity: (!isImport || showAdvanced) ? 1 : 0,
          transition: "max-height var(--transition-duration) var(--transition-easing), opacity var(--transition-duration) var(--transition-easing)",
        }}
      >
        {/* Audio Source */}
        <div className="flex items-center gap-4 mb-3">
          <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>音频来源</span>
          <label className="flex items-center gap-1.5 text-sm cursor-pointer" style={{ color: "var(--text-primary)" }}>
            <input
              type="radio"
              name={`batchAudioMode-${index}`}
              checked={config.audioMode === "tts"}
              onChange={() => updateConfig({ audioMode: "tts" })}
            />
            TTS 生成
          </label>
          <label className="flex items-center gap-1.5 text-sm cursor-pointer" style={{ color: "var(--text-primary)" }}>
            <input
              type="radio"
              name={`batchAudioMode-${index}`}
              checked={config.audioMode === "upload"}
              onChange={() => updateConfig({ audioMode: "upload" })}
            />
            上传音频
          </label>
        </div>
        {config.audioMode === "upload" && (
          <div className="flex items-center gap-3 mb-3">
            <label
              className="border-2 border-dashed rounded-lg px-6 py-3 text-sm cursor-pointer"
              style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}
            >
              <input
                type="file"
                accept="audio/*"
                className="hidden"
                onChange={(e) =>
                  updateConfig({ audioFile: e.target.files?.[0] || null })
                }
              />
              {config.audioFile ? config.audioFile.name : "点击选择音频文件"}
            </label>
            {config.audioFile && (
              <span className="text-xs" style={{ color: "var(--success)" }}>&#10003; 已选择</span>
            )}
          </div>
        )}

        {/* Cover Title */}
        <div className="flex items-center gap-4 mb-3 mt-3">
          <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>封面标题（可选）</span>
          <button
            type="button"
            className="text-xs border rounded px-2 py-1.5 disabled:opacity-50"
            style={{ color: "var(--text-secondary)", borderColor: "var(--border-default)" }}
            disabled={coverBtnDisabled}
            title={coverBtnTitle}
            onClick={handleGenerateCoverTitle}
          >
            {coverCooldown ? "冷却中（5s）..." : config.productionMode === "generate" ? "需先输入文案才能生成" : "自动生成标题"}
          </button>
        </div>
        <div className="flex items-center gap-3 flex-wrap mb-3">
          <input
            type="text"
            className="border rounded-lg px-3 py-2 text-sm min-w-[220px] flex-1 max-w-xs"
            style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
            placeholder="输入封面标题（留空则不显示）"
            value={config.coverTitleText}
            onChange={(e) => updateConfig({ coverTitleText: e.target.value })}
          />
          <input
            type="text"
            className="border rounded-lg px-3 py-2 text-sm min-w-[180px]"
            style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
            placeholder="高亮关键词，用逗号分隔"
            value={config.coverHighlightWords}
            onChange={(e) => updateConfig({ coverHighlightWords: e.target.value })}
          />
        </div>

        {/* Background Music */}
        <div className="flex items-center gap-4 mb-3 mt-3">
          <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>背景音乐（可选）</span>
        </div>
        <div className="flex items-center gap-3 flex-wrap mb-3">
          <select
            className="border rounded-lg px-3 py-1.5 text-sm min-w-[200px]"
            style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
            value={config.musicPath}
            onChange={(e) => updateConfig({ musicPath: e.target.value })}
          >
            <option value="">-- 选择背景音乐 --</option>
            {musicTracks.map((t) => (
              <option key={t.relative_path} value={t.relative_path}>
                {t.filename}
                {t.duration_seconds != null ? ` (${Math.floor(t.duration_seconds)}s)` : ""}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="text-xs border rounded px-2 py-1.5"
            style={{ color: "var(--text-secondary)", borderColor: "var(--border-default)" }}
            onClick={() => {
              if (musicTracks.length === 0) return;
              const pick = musicTracks[Math.floor(Math.random() * musicTracks.length)];
              updateConfig({ musicPath: pick.relative_path });
            }}
          >
            🎲 随机
          </button>
          {musicTracks.length === 0 && (
            <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
              音乐库为空，请将音频文件放入 workspace/music_library/
            </span>
          )}
          <label className="flex items-center gap-2 text-xs ml-4" style={{ color: "var(--text-secondary)" }}>
            音量
            <input
              type="range"
              min={0}
              max={100}
              value={config.musicVolume}
              onChange={(e) => updateConfig({ musicVolume: Number(e.target.value) })}
              className="w-24"
            />
            <span className="w-8 text-right">{config.musicVolume}%</span>
          </label>
        </div>
      </div>
    </div>
  );
}
