import { useState } from "react";
import type { ProductionMode, MusicTrack, ScriptTemplate } from "../types";
import { api } from "../api/client";

const PLATFORMS = [
  { key: "douyin", label: "抖音" },
  { key: "xiaohongshu", label: "小红书" },
  { key: "shipinhao", label: "视频号" },
  { key: "kuaishou", label: "快手" },
];

interface CreateJobFormProps {
  product: string;
  setProduct: (v: string) => void;
  brand: string;
  setBrand: (v: string) => void;
  platforms: string[];
  togglePlatform: (p: string) => void;
  jobName: string;
  setJobName: (v: string) => void;
  productionMode: ProductionMode;
  setProductionMode: (v: ProductionMode) => void;
  language: "mandarin" | "cantonese";
  setLanguage: (v: "mandarin" | "cantonese") => void;
  skipSubtitle: boolean;
  setSkipSubtitle: (v: boolean) => void;
  manualScript: string;
  setManualScript: (v: string) => void;
  audioMode: "tts" | "upload";
  setAudioMode: (v: "tts" | "upload") => void;
  audioFile: File | null;
  setAudioFile: (v: File | null) => void;
  musicTracks: MusicTrack[];
  selectedMusic: string;
  setSelectedMusic: (v: string) => void;
  musicVolume: number;
  setMusicVolume: (v: number) => void;
  coverTitleText: string;
  setCoverTitleText: (v: string) => void;
  coverHighlightWords: string;
  setCoverHighlightWords: (v: string) => void;
  /* templates */
  templates: ScriptTemplate[];
  selectedTemplateId: string;
  setSelectedTemplateId: (v: string) => void;
  templateVariableValues: Record<string, string>;
  setTemplateVariableValues: (v: Record<string, string>) => void;
  showTemplateSection: boolean;
  setShowTemplateSection: (v: boolean) => void;
  handleSelectTemplate: (tmplId: string) => Promise<void>;
  /* callbacks */
  onCreateJob: (form: SingleJobFormData) => Promise<void>;
  onError: (msg: string) => void;
}

export interface SingleJobFormData {
  product: string;
  brand?: string;
  platforms: string[];
  name?: string;
  mode: ProductionMode;
  manual_script: string;
  audio_source: "tts" | "upload";
  audioFile: File | null;
  music_track_path: string;
  music_volume: number;
  language: "mandarin" | "cantonese";
  skip_subtitle: boolean;
  cover_title_text: string;
  cover_highlight_words: string;
}

export default function CreateJobForm(props: CreateJobFormProps) {
  const {
    product, setProduct, brand, setBrand, platforms, togglePlatform,
    jobName, setJobName, productionMode, setProductionMode,
    language, setLanguage, skipSubtitle, setSkipSubtitle,
    manualScript, setManualScript, audioMode, setAudioMode,
    audioFile, setAudioFile, musicTracks, selectedMusic, setSelectedMusic,
    musicVolume, setMusicVolume, coverTitleText, setCoverTitleText,
    coverHighlightWords, setCoverHighlightWords,
    templates, selectedTemplateId, setSelectedTemplateId,
    templateVariableValues, setTemplateVariableValues,
    showTemplateSection, setShowTemplateSection, handleSelectTemplate,
    onCreateJob, onError,
  } = props;

  const [coverTitleCooldown, setCoverTitleCooldown] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const isImport = productionMode === "import";

  const handleApplyTemplate = async () => {
    if (!selectedTemplateId) return;
    try {
      const tmpl = templates.find((t) => t.id === selectedTemplateId);
      if (!tmpl) return;
      const slotContents: Record<string, string> = {};
      tmpl.slots.forEach((slot) => {
        slotContents[slot.label] = templateVariableValues[`slot_${slot.label}`] || "";
      });
      const res = await api.previewTemplate(selectedTemplateId, slotContents, templateVariableValues);
      setManualScript(res.rendered_script);
    } catch {
      onError("应用模板失败");
    }
  };

  const handleGenerateCoverTitle = async () => {
    if (coverTitleCooldown) return;
    const text = isImport ? manualScript : "";
    if (!text.trim()) return;
    setCoverTitleCooldown(true);
    try {
      const res = await api.generateCoverTitle({ script_text: text, product });
      setCoverTitleText(res.text);
      setCoverHighlightWords(res.highlight_words.join("，"));
    } catch {
      onError("生成封面标题失败，请稍后重试");
    } finally {
      setTimeout(() => setCoverTitleCooldown(false), 5000);
    }
  };

  const handleSubmit = async () => {
    await onCreateJob({
      product,
      brand: brand || undefined,
      platforms,
      name: jobName || undefined,
      mode: productionMode,
      manual_script: isImport ? manualScript : "",
      audio_source: audioMode,
      audioFile,
      music_track_path: selectedMusic,
      music_volume: musicVolume,
      language,
      skip_subtitle: skipSubtitle,
      cover_title_text: coverTitleText.trim(),
      cover_highlight_words: coverHighlightWords,
    });
  };

  const coverBtnDisabled = productionMode === "generate" || coverTitleCooldown;
  const coverBtnTitle = coverTitleCooldown
    ? "冷却中，请等待 5 秒"
    : productionMode === "generate"
      ? "智能生成模式下由 LLM 自动生成封面标题，无需手动生成"
      : "";

  return (
    <>
      {/* shared fields: product + brand + name + platforms */}
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
        <label className="grid gap-1.5 text-xs min-w-[200px]" style={{ color: "var(--text-secondary)" }}>
          任务名称（可选）
          <input
            type="text"
            className="border rounded-lg px-3 py-2 text-sm"
            style={{ background: "var(--bg-input)", borderColor: "var(--border-default)", color: "var(--text-primary)" }}
            placeholder="默认使用产品名"
            value={jobName}
            onChange={(e) => setJobName(e.target.value)}
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

      {/* production mode + toggles */}
      <div className="mt-4 pt-4 border-t" style={{ borderColor: "var(--border-default)" }}>
        <div className="flex items-center gap-4 mb-3">
          <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>生产模式</span>
          <div className="flex rounded-lg border overflow-hidden" style={{ borderColor: "var(--border-default)" }}>
            <button
              type="button"
              className="px-4 py-1.5 text-sm font-medium"
              style={
                productionMode === "generate"
                  ? { background: "var(--btn-primary-bg)", color: "var(--btn-primary-text)" }
                  : { background: "var(--bg-card)", color: "var(--text-secondary)" }
              }
              onClick={() => setProductionMode("generate")}
            >
              智能生成
            </button>
            <button
              type="button"
              className="px-4 py-1.5 text-sm font-medium"
              style={
                productionMode === "import"
                  ? { background: "var(--btn-primary-bg)", color: "var(--btn-primary-text)" }
                  : { background: "var(--bg-card)", color: "var(--text-secondary)" }
              }
              onClick={() => setProductionMode("import")}
            >
              手动导入
            </button>
          </div>
          <label className="flex items-center gap-1.5 text-sm cursor-pointer ml-4" style={{ color: "var(--text-primary)" }}>
            <input
              type="checkbox"
              checked={language === "cantonese"}
              onChange={(e) => setLanguage(e.target.checked ? "cantonese" : "mandarin")}
            />
            粤语版
          </label>
          <label className="flex items-center gap-1.5 text-sm cursor-pointer ml-4" style={{ color: "var(--text-primary)" }}>
            <input
              type="checkbox"
              checked={skipSubtitle}
              onChange={(e) => setSkipSubtitle(e.target.checked)}
            />
            跳过字幕
          </label>
        </div>

        {/* Import: script textarea + template */}
        {isImport && (
          <div>
            {/* Script Template Selector */}
            <div className="mb-3">
              <label className="flex items-center gap-2 text-xs mb-2" style={{ color: "var(--text-secondary)" }}>
                <input
                  type="checkbox"
                  checked={showTemplateSection}
                  onChange={(e) => {
                    setShowTemplateSection(e.target.checked);
                    if (!e.target.checked) setSelectedTemplateId("");
                  }}
                />
                使用脚本模板
              </label>
              {showTemplateSection && (
                <div className="border rounded-lg p-4 mb-3 space-y-3" style={{ background: "var(--bg-page)", borderColor: "var(--border-default)" }}>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>选择模板</label>
                    <select
                      className="w-full border rounded-lg px-3 py-2 text-sm"
                      style={{ background: "var(--bg-card)", borderColor: "var(--border-default)", color: "var(--text-primary)" }}
                      value={selectedTemplateId}
                      onChange={(e) => handleSelectTemplate(e.target.value)}
                    >
                      <option value="">-- 选择模板 --</option>
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </div>
                  {selectedTemplateId && (() => {
                    const tmpl = templates.find((t) => t.id === selectedTemplateId);
                    if (!tmpl) return null;
                    return (
                      <>
                        {tmpl.slots.map((slot, idx) => (
                          <div key={`slot-${idx}`}>
                            <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
                              {slot.label || `片段 #${idx + 1}`}
                              {slot.required && <span style={{ color: "var(--danger)" }} className="ml-1">*</span>}
                              <span className="ml-1" style={{ color: "var(--text-secondary)" }}>({slot.hint || ""})</span>
                            </label>
                            <textarea
                              className="w-full border rounded-lg px-3 py-2 text-sm resize-none"
                              style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
                              rows={2}
                              placeholder={slot.hint || `输入${slot.label}内容`}
                              value={templateVariableValues[`slot_${slot.label}`] || ""}
                              onChange={(e) =>
                                setTemplateVariableValues({
                                  ...templateVariableValues,
                                  [`slot_${slot.label}`]: e.target.value,
                                })
                              }
                            />
                          </div>
                        ))}
                        {tmpl.variables.map((v, idx) => (
                          <div key={`var-${idx}`}>
                            <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
                              {v.label || v.name}
                              <span className="ml-1" style={{ color: "var(--text-secondary)" }}>
                                ({v.source === "product_config" ? "自动从产品配置填充" : v.source === "manual" ? "手动输入" : "知识库"})
                              </span>
                            </label>
                            <input
                              type="text"
                              className="w-full border rounded-lg px-3 py-2 text-sm"
                              style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
                              placeholder={`输入${v.label || v.name}`}
                              value={templateVariableValues[v.name] || ""}
                              onChange={(e) =>
                                setTemplateVariableValues({
                                  ...templateVariableValues,
                                  [v.name]: e.target.value,
                                })
                              }
                              disabled={v.source === "product_config"}
                            />
                          </div>
                        ))}
                        <button
                          className="px-4 py-2 text-sm rounded-lg"
                          style={{ background: "var(--btn-primary-bg)", color: "var(--btn-primary-text)" }}
                          onClick={handleApplyTemplate}
                        >
                          应用模板到脚本
                        </button>
                      </>
                    );
                  })()}
                </div>
              )}
            </div>
            <textarea
              className="w-full border rounded-lg px-3 py-2 text-sm min-h-[120px]"
              style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
              placeholder="请输入文案内容（150-200字）..."
              value={manualScript}
              onChange={(e) => setManualScript(e.target.value)}
            />
          </div>
        )}

        {!isImport && (
          <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
            LLM 将根据产品信息自动生成口播脚本
          </p>
        )}
      </div>

      {/* progressive disclosure: "更多设置" for Import mode */}
      {isImport && (
        <div className="mt-3">
          <button
            type="button"
            className="text-xs font-medium flex items-center gap-1"
            style={{ color: "var(--text-secondary)" }}
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            <span style={{
              display: "inline-block",
              transform: showAdvanced ? "rotate(90deg)" : "rotate(0deg)",
              transition: "transform 150ms ease",
            }}>
              &#9654;
            </span>
            更多设置
          </button>
        </div>
      )}

      {/* advanced section (always visible in Generate mode, collapsible in Import mode) */}
      <div
        style={{
          overflow: "hidden",
          maxHeight: (!isImport || showAdvanced) ? "2000px" : "0px",
          opacity: (!isImport || showAdvanced) ? 1 : 0,
          transition: "max-height 150ms ease, opacity 150ms ease",
        }}
      >
        {/* Audio Source */}
        <div className="mt-4 pt-4 border-t" style={{ borderColor: "var(--border-default)" }}>
          <div className="flex items-center gap-4 mb-3">
            <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>音频来源</span>
            <label className="flex items-center gap-1.5 text-sm cursor-pointer" style={{ color: "var(--text-primary)" }}>
              <input
                type="radio"
                name="audioMode"
                checked={audioMode === "tts"}
                onChange={() => setAudioMode("tts")}
              />
              TTS 生成
            </label>
            <label className="flex items-center gap-1.5 text-sm cursor-pointer" style={{ color: "var(--text-primary)" }}>
              <input
                type="radio"
                name="audioMode"
                checked={audioMode === "upload"}
                onChange={() => setAudioMode("upload")}
              />
              上传音频
            </label>
          </div>
          {audioMode === "upload" && (
            <div className="flex items-center gap-3">
              <label
                className="border-2 border-dashed rounded-lg px-6 py-4 text-sm cursor-pointer"
                style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}
              >
                <input
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
                />
                {audioFile ? audioFile.name : "点击选择音频文件"}
              </label>
              {audioFile && (
                <span className="text-xs" style={{ color: "var(--success)" }}>&#10003; 已选择</span>
              )}
            </div>
          )}
        </div>

        {/* Cover Title */}
        <div className="mt-4 pt-4 border-t" style={{ borderColor: "var(--border-default)" }}>
          <div className="flex items-center gap-4 mb-3">
            <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>封面标题（可选）</span>
            <button
              type="button"
              className="text-xs border rounded px-2 py-1.5 disabled:opacity-50"
              style={{ color: "var(--text-secondary)", borderColor: "var(--border-default)" }}
              disabled={coverBtnDisabled}
              title={coverBtnTitle}
              onClick={handleGenerateCoverTitle}
            >
              {coverTitleCooldown ? "冷却中（5s）..." : productionMode === "generate" ? "需先输入文案才能生成" : "自动生成标题"}
            </button>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <input
              type="text"
              className="border rounded-lg px-3 py-2 text-sm min-w-[260px] flex-1 max-w-md"
              style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
              placeholder="输入封面标题（留空则不显示）"
              value={coverTitleText}
              onChange={(e) => setCoverTitleText(e.target.value)}
            />
            <input
              type="text"
              className="border rounded-lg px-3 py-2 text-sm min-w-[200px]"
              style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
              placeholder="高亮关键词，用逗号分隔"
              value={coverHighlightWords}
              onChange={(e) => setCoverHighlightWords(e.target.value)}
            />
          </div>
        </div>

        {/* Background Music */}
        <div className="mt-4 pt-4 border-t" style={{ borderColor: "var(--border-default)" }}>
          <div className="flex items-center gap-4 mb-3">
            <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>背景音乐（可选）</span>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <select
              className="border rounded-lg px-3 py-1.5 text-sm min-w-[200px]"
              style={{ borderColor: "var(--border-default)", background: "var(--bg-input)", color: "var(--text-primary)" }}
              value={selectedMusic}
              onChange={(e) => setSelectedMusic(e.target.value)}
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
                setSelectedMusic(pick.relative_path);
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
                value={musicVolume}
                onChange={(e) => setMusicVolume(Number(e.target.value))}
                className="w-24"
              />
              <span className="w-8 text-right">{musicVolume}%</span>
            </label>
          </div>
        </div>
      </div>

      {/* submit */}
      <div className="mt-4 pt-4 border-t flex justify-end" style={{ borderColor: "var(--border-default)" }}>
        <button
          className="px-8 py-3 rounded-lg text-[15px] font-semibold"
          style={{ background: "var(--btn-primary-bg)", color: "var(--btn-primary-text)" }}
          onClick={handleSubmit}
        >
          创建并开始生产
        </button>
      </div>
    </>
  );
}
