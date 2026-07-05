import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import type { ProviderConfig, ProviderOptions, ProviderField } from "../types";

const SECTIONS = [
  { key: "llm", label: "LLM" },
  { key: "tts", label: "TTS" },
  { key: "vision", label: "Vision（素材识别）" },
  { key: "text_to_image", label: "文生图" },
  { key: "image_to_video", label: "图生视频" },
];

export default function ConfigPage() {
  const [config, setConfig] = useState<ProviderConfig | null>(null);
  const [options, setOptions] = useState<ProviderOptions | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [c, o] = await Promise.all([api.getConfig(), api.getConfigOptions()]);
      setConfig(c);
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

  const handleSectionSave = async (section: string) => {
    if (!config) return;
    setSaving(section);
    setSaveMsg(null);
    try {
      await api.saveConfig(config);
      setSaveMsg(`${SECTIONS.find((s) => s.key === section)?.label} 配置已保存`);
    } catch (e) {
      setSaveMsg(`保存失败：${e instanceof Error ? e.message : "未知错误"}`);
    }
    setSaving(null);
  };

  if (!config || !options) {
    return <div className="text-center py-12" style={{ color: "var(--text-secondary)" }}>加载配置中...</div>;
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">系统配置</h1>
      {saveMsg && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm" style={
          saveMsg.includes("失败")
            ? { background: "#f8514922", border: "1px solid var(--danger)", color: "var(--danger)" }
            : { background: "var(--bg-tag-green)", border: "1px solid var(--success)", color: "var(--success)" }
        }>
          {saveMsg}
        </div>
      )}
      {SECTIONS.map(({ key, label }) => {
        const sectionData = config.providers[key];
        const sectionOpts = options.providers[key];
        const selected = sectionData?.selected || "";

        return (
          <section key={key} className="border rounded-xl p-5 mb-6" style={{ background: "var(--bg-page)" }}>
            <h2 className="font-semibold mb-4">{label}</h2>

            <label className="grid gap-1 text-xs mb-3" style={{ color: "var(--text-secondary)" }}>
              Provider
              <select
                className="border rounded-lg px-3 py-2 text-sm" style={{ background: "var(--bg-card)" }}
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
                        className="border rounded-lg px-3 py-2 text-sm" style={{ background: "var(--bg-card)" }}
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
                        className="border rounded-lg px-3 py-2 text-sm" style={{ background: "var(--bg-card)" }}
                        type={field.secret ? "password" : "text"}
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

            <button
              className="mt-3 px-4 py-2 rounded-md text-xs transition-colors"
              style={saving === key ? { background: "#6e7681", color: "#fff" } : { background: "var(--accent)", color: "#fff" }}
              disabled={saving === key}
              onClick={() => handleSectionSave(key)}
            >
              {saving === key ? "保存中..." : `保存 ${label} 配置`}
            </button>
          </section>
        );
      })}
    </div>
  );
}
