import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import { useProducts } from "../ProductContext";
import type { ProductConfig } from "../types";

interface FormErrors {
  default_name?: string;
  default_brand?: string;
}

const DEFAULT_CONFIG: ProductConfig = {
  default_name: "",
  default_brand: "",
  script: {
    scene: "",
    material: "",
    system_prompt: "",
  },
};

const inputStyle = {
  width: "100%",
  padding: "8px 16px",
  border: "1px solid var(--border-default)",
  borderRadius: "var(--radius)",
  fontSize: "var(--font-size-base)",
  background: "var(--bg-input, var(--bg-card))",
  color: "var(--text-primary)",
} as React.CSSProperties;

const textareaStyle = {
  ...inputStyle,
  padding: "12px 16px",
  resize: "none" as const,
};

const labelStyle = {
  display: "block",
  fontSize: "var(--font-size-base)",
  fontWeight: 500,
  color: "var(--text-primary)",
  marginBottom: "8px",
} as React.CSSProperties;

const hintStyle = {
  marginTop: "4px",
  fontSize: "var(--font-size-sm)",
  color: "var(--text-tertiary)",
} as React.CSSProperties;

const errorTextStyle = {
  marginTop: "4px",
  fontSize: "var(--font-size-sm)",
  color: "var(--danger)",
} as React.CSSProperties;

export default function ProductConfigForm() {
  const { products, activeProductId, activeProductName, switchProduct } = useProducts();
  const [config, setConfig] = useState<ProductConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [newProductName, setNewProductName] = useState("");

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await api.getProductConfig();
      setConfig(data);
    } catch {
      setLoadError("加载产品配置失败");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const validate = (): boolean => {
    const newErrors: FormErrors = {};

    if (!config.default_name || config.default_name.trim() === "") {
      newErrors.default_name = "产品名不能为空";
    } else if (config.default_name.length > 50) {
      newErrors.default_name = "产品名不能超过50字";
    }

    if (!config.default_brand || config.default_brand.trim() === "") {
      newErrors.default_brand = "品牌名不能为空";
    } else if (config.default_brand.length > 50) {
      newErrors.default_brand = "品牌名不能超过50字";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const result = await api.saveProductConfig(config);
      setConfig(result);
      setSaveMsg("配置已保存");
      setTimeout(() => setSaveMsg(null), 3000);
    } catch {
      setSaveMsg("保存失败");
    }
    setSaving(false);
  };

  const handleReset = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      await api.resetProductConfig();
      setSaveMsg("配置已重置");
      setTimeout(() => setSaveMsg(null), 3000);
      await loadConfig();
    } catch {
      setSaveMsg("重置失败");
    }
    setSaving(false);
  };

  const updateField = (field: keyof ProductConfig, value: string) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
    if (errors[field as keyof FormErrors]) {
      setErrors((prev) => ({ ...prev, [field]: undefined }));
    }
  };

  const updateScriptField = (field: string, value: string) => {
    setConfig((prev) => ({
      ...prev,
      script: { ...prev.script, [field]: value },
    }));
  };

  if (loading) {
    return <div className="text-center py-12" style={{ color: "var(--text-secondary)" }}>加载配置中...</div>;
  }

  // Empty state: no products configured
  if (products.length === 0 && !showNewForm) {
    return (
      <div>
        <h1 className="text-xl font-bold mb-4" style={{ color: "var(--text-primary)" }}>产品配置</h1>
        <div
          className="text-center py-16 border border-dashed rounded-xl"
          style={{
            background: "var(--bg-card)",
            borderColor: "var(--border-default)",
          }}
        >
          <div className="text-4xl mb-3">📦</div>
          <h2 className="text-lg font-semibold mb-2" style={{ color: "var(--text-primary)" }}>暂无产品配置</h2>
          <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>
            创建一个产品配置，用于脚本生成和素材检索
          </p>
          <button
            className="px-6 py-3 text-[var(--text-inverse)] font-medium rounded-xl hover:brightness-110 transition-colors"
            style={{ background: "var(--accent)" }}
            onClick={() => setShowNewForm(true)}
          >
            新建产品
          </button>
        </div>
      </div>
    );
  }

  // New product creation form
  if (showNewForm) {
    return (
      <div>
        <h1 className="text-xl font-bold mb-6" style={{ color: "var(--text-primary)" }}>新建产品配置</h1>
        <div
          className="rounded-xl border p-6 max-w-lg"
          style={{
            background: "var(--bg-card)",
            borderColor: "var(--border-default)",
          }}
        >
          <label style={labelStyle}>
            产品名称 <span style={{ color: "var(--danger)" }}>*</span>
          </label>
          <input
            type="text"
            className="w-full px-4 py-2 rounded-lg text-sm mb-4"
            style={{ ...inputStyle, marginBottom: "16px" }}
            placeholder="输入产品名称，如：羊肚菌"
            value={newProductName}
            onChange={(e) => setNewProductName(e.target.value)}
          />
          <div className="flex gap-3">
            <button
              className="px-6 py-3 text-[var(--text-inverse)] font-medium rounded-xl hover:brightness-110 disabled:opacity-50 transition-colors"
              style={{ background: "var(--accent)" }}
              disabled={!newProductName.trim()}
              onClick={async () => {
                const id = newProductName.trim().toLowerCase().replace(/\s+/g, "_");
                await api.switchProduct(id);
                await switchProduct(id);
                await loadConfig();
                setShowNewForm(false);
              }}
            >
              创建并编辑
            </button>
            <button
              className="px-6 py-3 font-medium rounded-xl hover:brightness-110 transition-colors"
              style={{ background: "var(--bg-page)", color: "var(--text-primary)" }}
              onClick={() => setShowNewForm(false)}
            >
              取消
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
          产品配置
          {activeProductName && (
            <span className="ml-2 text-base font-normal" style={{ color: "var(--text-secondary)" }}>
              — {activeProductName}
            </span>
          )}
        </h1>
        <div className="text-xs" style={{ color: "var(--text-tertiary)" }}>
          ID: {activeProductId}
        </div>
      </div>

      {loadError && (
        <div
          className="mb-4 px-4 py-3 rounded-lg text-sm"
          style={{
            background: "var(--danger-bg)",
            borderColor: "var(--danger-border)",
            color: "var(--danger)",
          }}
        >
          {loadError}
        </div>
      )}

      {saveMsg && (
        <div
          className="mb-4 px-4 py-3 rounded-lg text-sm"
          style={
            saveMsg.includes("失败")
              ? {
                  background: "var(--danger-bg)",
                  borderColor: "var(--danger-border)",
                  color: "var(--danger)",
                }
              : {
                  background: "var(--success-bg)",
                  borderColor: "var(--success-border)",
                  color: "var(--success)",
                }
          }
        >
          {saveMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-6">
          {/* 基本信息 */}
          <section
            className="rounded-xl border p-6"
            style={{ background: "var(--bg-card)", borderColor: "var(--border-default)" }}
          >
            <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--text-primary)" }}>基本信息</h2>
            <div className="space-y-4">
              <div>
                <label style={labelStyle}>
                  产品名 <span style={{ color: "var(--danger)" }}>*</span>
                </label>
                <input
                  type="text"
                  className="w-full px-4 py-2 rounded-lg text-sm"
                  style={{
                    ...inputStyle,
                    ...(errors.default_name
                      ? { borderColor: "var(--danger-border)", background: "var(--danger-bg)" }
                      : {}),
                  }}
                  placeholder="输入产品名称"
                  value={config.default_name}
                  onChange={(e) => updateField("default_name", e.target.value)}
                />
                {errors.default_name && (
                  <p style={errorTextStyle}>{errors.default_name}</p>
                )}
                <p style={hintStyle}>
                  用于脚本生成和素材检索的默认产品名
                </p>
              </div>

              <div>
                <label style={labelStyle}>
                  品牌名 <span style={{ color: "var(--danger)" }}>*</span>
                </label>
                <input
                  type="text"
                  className="w-full px-4 py-2 rounded-lg text-sm"
                  style={{
                    ...inputStyle,
                    ...(errors.default_brand
                      ? { borderColor: "var(--danger-border)", background: "var(--danger-bg)" }
                      : {}),
                  }}
                  placeholder="输入品牌名称"
                  value={config.default_brand}
                  onChange={(e) => updateField("default_brand", e.target.value)}
                />
                {errors.default_brand && (
                  <p style={errorTextStyle}>{errors.default_brand}</p>
                )}
                <p style={hintStyle}>
                  品牌名，用于脚本生成
                </p>
              </div>
            </div>
          </section>
        </div>

        <div className="space-y-6">
          {/* 内容配置 */}
          <section
            className="rounded-xl border p-6"
            style={{ background: "var(--bg-card)", borderColor: "var(--border-default)" }}
          >
            <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--text-primary)" }}>内容配置</h2>
            <div className="space-y-4">
              <div>
                <label style={labelStyle}>
                  场景描述
                </label>
                <textarea
                  className="w-full px-4 py-3 rounded-lg text-sm"
                  style={{ ...textareaStyle, resize: "none" }}
                  rows={3}
                  placeholder="描述视频场景内容"
                  value={config.script.scene}
                  onChange={(e) => updateScriptField("scene", e.target.value)}
                />
                <p style={hintStyle}>
                  描述脚本生成的场景方向，如：食材展示、烹饪过程、成品呈现
                </p>
              </div>

              <div>
                <label style={labelStyle}>
                  素材描述
                </label>
                <textarea
                  className="w-full px-4 py-3 rounded-lg text-sm"
                  style={{ ...textareaStyle, resize: "none" }}
                  rows={3}
                  placeholder="描述所需素材内容"
                  value={config.script.material}
                  onChange={(e) => updateScriptField("material", e.target.value)}
                />
                <p style={hintStyle}>
                  描述素材检索的方向，如：食材近景、清洗处理、烹饪翻炒
                </p>
              </div>

              <div>
                <label style={labelStyle}>
                  系统提示词
                </label>
                <textarea
                  className="w-full px-4 py-3 rounded-lg text-sm"
                  style={{ ...textareaStyle, resize: "none" }}
                  rows={4}
                  placeholder="系统提示词，LLM 生成脚本时的角色设定"
                  value={config.script.system_prompt}
                  onChange={(e) => updateScriptField("system_prompt", e.target.value)}
                />
                <p style={hintStyle}>
                  LLM 生成脚本时的角色设定和约束。不填则使用系统默认值。
                </p>
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-4 mt-6">
        <button
          className="px-6 py-3 text-[var(--text-inverse)] font-medium rounded-xl hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          style={{ background: "var(--accent)" }}
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? "保存中..." : "保存配置"}
        </button>
        <button
          className="px-6 py-3 font-medium rounded-xl hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          style={{ background: "var(--bg-page)", color: "var(--text-primary)" }}
          onClick={handleReset}
          disabled={saving}
        >
          重置为默认值
        </button>
      </div>
    </div>
  );
}
