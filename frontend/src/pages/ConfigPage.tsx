import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import type { ProviderConfig, ProviderOptions, ProviderField } from "../types";

interface SectionDef {
  key: string;
  label: string;
  color: string;
  icon: (color: string) => React.ReactNode;
  cssVar: string;
}

const SECTIONS: SectionDef[] = [
  {
    key: "llm",
    label: "LLM",
    color: "#3b82f6",
    cssVar: "--section-llm-color",
    icon: (color: string) => (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
      </svg>
    ),
  },
  {
    key: "tts",
    label: "TTS",
    color: "#22c55e",
    cssVar: "--section-tts-color",
    icon: (color: string) => (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
      </svg>
    ),
  },
  {
    key: "vision",
    label: "Vision",
    color: "#7c3aed",
    cssVar: "--section-vision-color",
    icon: (color: string) => (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    ),
  },
  {
    key: "text_to_image",
    label: "文生图",
    color: "#f59e0b",
    cssVar: "--section-text_to_image-color",
    icon: (color: string) => (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
        <circle cx="9" cy="9" r="2" />
        <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
      </svg>
    ),
  },
  {
    key: "image_to_video",
    label: "图生视频",
    color: "#0891b2",
    cssVar: "--section-image_to_video-color",
    icon: (color: string) => (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="6" width="20" height="12" rx="2" ry="2" />
        <path d="m10 10 4 2-4 2z" />
      </svg>
    ),
  },
];

const inputStyle: React.CSSProperties = {
  backgroundColor: "var(--bg-input)",
  borderColor: "var(--input-border)",
  color: "var(--input-text)",
};

function selectFirstProviders(c: ProviderConfig, o: ProviderOptions): ProviderConfig {
  const next = structuredClone(c);
  for (const { key } of SECTIONS) {
    const section = next.providers[key];
    const opts = o.providers[key];
    if (!section.selected && opts) {
      const first = Object.keys(opts.providers)[0];
      if (first) {
        section.selected = first;
      }
    }
  }
  return next;
}

export default function ConfigPage() {
  const [config, setConfig] = useState<ProviderConfig | null>(null);
  const [options, setOptions] = useState<ProviderOptions | null>(null);
  const [activeTab, setActiveTab] = useState<string>("llm");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [c, o] = await Promise.all([api.getConfig(), api.getConfigOptions()]);
      const initialized = selectFirstProviders(c, o);
      setConfig(initialized);
      setOptions(o);
    } catch (e) {
      setSaveMsg("加载配置失败，请重试");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const updateField = (section: string, provider: string, field: string, value: unknown) => {
    if (!config) return;
    const next = structuredClone(config);
    const sectionData = next.providers[section];
    if (!sectionData.providers[provider]) {
      sectionData.providers[provider] = {};
    }
    sectionData.providers[provider] = {
      ...sectionData.providers[provider],
      [field]: value,
    } as Record<string, unknown>;
    setConfig(next);
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      await api.saveConfig(config);
      setSaveMsg("配置已保存");
    } catch (e) {
      setSaveMsg(`保存失败：${e instanceof Error ? e.message : "未知错误"}`);
    }
    setSaving(false);
  };

  if (!config || !options) {
    return <div className="text-center py-12" style={{ color: "var(--text-secondary)" }}>加载配置中...</div>;
  }

  const activeSection = SECTIONS.find((s) => s.key === activeTab) ?? SECTIONS[0];
  const key = activeSection.key;
  const sectionData = config.providers[key];
  const sectionOpts = options.providers[key];
  const selected = sectionData?.selected || "";

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>系统配置</h1>
        <button
          className="px-4 py-2 rounded-md text-xs font-medium transition-colors"
          style={saving ? { background: "var(--text-tertiary)", color: "var(--text-inverse)" } : { background: "var(--accent)", color: "var(--text-inverse)" }}
          disabled={saving}
          onClick={handleSave}
        >
          {saving ? "保存中..." : "保存配置"}
        </button>
      </div>

      {saveMsg && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm border" style={
          saveMsg.includes("失败")
            ? { background: "var(--alert-red-muted)", borderColor: "var(--danger)", color: "var(--danger)" }
            : { background: "var(--bg-tag-green)", borderColor: "var(--success)", color: "var(--success)" }
        }>
          {saveMsg}
        </div>
      )}

      <div className="flex gap-2 mb-6 border-b" style={{ borderColor: "var(--border-default)" }} role="tablist">
        {SECTIONS.map(({ key: sectionKey, label, cssVar, icon }) => {
          const active = activeTab === sectionKey;
          const sectionColorVar = `var(${cssVar})`;
          const sectionColorMutedVar = `var(${cssVar}-muted)`;
          return (
            <button
              key={sectionKey}
              role="tab"
              aria-selected={active}
              className="flex items-center gap-[var(--tab-gap,8px)] px-[var(--tab-padding-x,16px)] py-[var(--tab-padding-y,10px)] text-[var(--tab-font-size,0.875rem)] font-medium border-b-2 transition-colors"
              style={{
                borderColor: active ? sectionColorVar : "transparent",
                color: active ? sectionColorVar : "var(--text-secondary)",
                background: active ? sectionColorMutedVar : "transparent",
              }}
              onClick={() => setActiveTab(sectionKey)}
            >
              <span style={{ color: sectionColorVar }}>{icon(sectionColorVar)}</span>
              {label}
            </button>
          );
        })}
      </div>

      <section
        key={key}
        className="border rounded-xl p-5"
        style={{ background: "var(--bg-page)", borderColor: "var(--border-default)" }}
      >
        <h2 className="font-semibold mb-4" style={{ color: "var(--text-primary)" }}>{activeSection.label}</h2>

        <label className="grid gap-1 text-xs mb-3" style={{ color: "var(--text-secondary)" }}>
          Provider
          <select
            className="border rounded-lg px-3 py-2 text-sm"
            style={inputStyle}
            value={selected}
            onChange={(e) => {
              const next = structuredClone(config);
              next.providers[key].selected = e.target.value;
              setConfig(next);
            }}
          >
            <option value="">未选择</option>
            {Object.entries(sectionOpts?.providers || {}).map(([k, v]) => (
              <option key={k} value={k}>
                {(v as { label: string }).label || k}
              </option>
            ))}
          </select>
        </label>

        {selected &&
          sectionOpts?.providers[selected] &&
          (sectionOpts.providers[selected] as { fields: ProviderField[] }).fields.map(
            (field) => (
              <label key={field.name} className="grid gap-1 text-xs mb-3" style={{ color: "var(--text-secondary)" }}>
                {field.label}
                {field.kind === "select" ? (
                  <select
                    className="border rounded-lg px-3 py-2 text-sm"
                    style={inputStyle}
                    value={
                      ((sectionData?.providers[selected]?.[field.name]) as string) || ""
                    }
                    onChange={(e) =>
                      updateField(key, selected, field.name, e.target.value)
                    }
                  >
                    {(field.options || []).map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="border rounded-lg px-3 py-2 text-sm"
                    style={inputStyle}
                    type={field.secret ? "password" : "text"}
                    placeholder="请输入"
                    value={
                      ((sectionData?.providers[selected]?.[field.name]) as string) || ""
                    }
                    onChange={(e) =>
                      updateField(key, selected, field.name, e.target.value)
                    }
                  />
                )}
              </label>
            )
          )}
      </section>
    </div>
  );
}
