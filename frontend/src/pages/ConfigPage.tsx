import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import type { ProviderConfig, ProviderOptions, ProviderField } from "../types";

const SECTIONS = [
  { key: "llm", label: "LLM" },
  { key: "tts", label: "TTS" },
  { key: "text_to_image", label: "文生图" },
  { key: "image_to_video", label: "图生视频" },
];

export default function ConfigPage() {
  const [config, setConfig] = useState<ProviderConfig | null>(null);
  const [options, setOptions] = useState<ProviderOptions | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [c, o] = await Promise.all([api.getConfig(), api.getConfigOptions()]);
      setConfig(c);
      setOptions(o);
    } catch {
      /* silently fail */
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
    try {
      await api.saveConfig(config);
    } catch {
      /* silently fail */
    }
    setSaving(null);
  };

  if (!config || !options) {
    return <div className="text-center py-12 text-gray-400">加载配置中...</div>;
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">系统配置</h1>
      {SECTIONS.map(({ key, label }) => {
        const sectionData = config.providers[key];
        const sectionOpts = options.providers[key];
        const selected = sectionData?.selected || "";

        return (
          <section key={key} className="bg-gray-50 border rounded-xl p-5 mb-6">
            <h2 className="font-semibold mb-4">{label}</h2>

            <label className="grid gap-1 text-xs text-gray-500 mb-3">
              Provider
              <select
                className="border rounded-lg px-3 py-2 text-sm bg-white"
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
                  <label key={field.name} className="grid gap-1 text-xs text-gray-500 mb-3">
                    {field.label}
                    {field.kind === "select" ? (
                      <select
                        className="border rounded-lg px-3 py-2 text-sm bg-white"
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
                        className="border rounded-lg px-3 py-2 text-sm bg-white"
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
              className={`mt-3 text-white px-4 py-2 rounded-lg text-sm transition-colors ${
                saving === key ? "bg-gray-400" : "bg-blue-600 hover:bg-blue-700"
              }`}
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
