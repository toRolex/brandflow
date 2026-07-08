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
  const { products, activeProductId, activeProductName, switchProduct, refreshProducts, createProduct, renameProduct, deleteProduct } = useProducts();
  const [config, setConfig] = useState<ProductConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [newProductName, setNewProductName] = useState("");
  const [editingProductId, setEditingProductId] = useState<string>("");
  const [renamingProductId, setRenamingProductId] = useState<string>("");
  const [renameValue, setRenameValue] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string>("");

  const loadConfig = useCallback(async (productId?: string) => {
    setLoading(true);
    setLoadError(null);
    try {
      let data: ProductConfig;
      if (productId) {
        data = await api.getProductConfigById(productId);
        setEditingProductId(productId);
      } else {
        data = await api.getProductConfig();
        const id = (data as Record<string, unknown>).id as string || activeProductId;
        setEditingProductId(id);
      }
      setConfig(data);
    } catch {
      setLoadError("加载产品配置失败");
    }
    setLoading(false);
  }, [activeProductId]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const handleSelectProduct = async (productId: string) => {
    await loadConfig(productId);
  };

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
      let result: ProductConfig;
      if (editingProductId && editingProductId !== activeProductId) {
        result = await api.saveProductConfigById(editingProductId, config);
      } else {
        result = await api.saveProductConfig(config);
      }
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
            placeholder="输入产品名称，如：示例产品"
            value={newProductName}
            onChange={(e) => setNewProductName(e.target.value)}
          />
          <div className="flex gap-3">
            <button
              className="px-6 py-3 text-[var(--text-inverse)] font-medium rounded-xl hover:brightness-110 disabled:opacity-50 transition-colors"
              style={{ background: "var(--accent)" }}
              disabled={!newProductName.trim()}
              onClick={async () => {
                await createProduct(newProductName.trim());
                await refreshProducts();
                setShowNewForm(false);
                setNewProductName("");
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

  const isEditingActive = editingProductId === activeProductId;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
          产品配置
          {activeProductName && (
            <span className="ml-2 text-base font-normal" style={{ color: "var(--text-secondary)" }}>
              — 活跃：{activeProductName}
            </span>
          )}
        </h1>
        <div className="text-xs" style={{ color: "var(--text-tertiary)" }}>
          活跃产品 ID: {activeProductId}
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

      <div className="flex gap-6">
        {/* Product list sidebar */}
        <div className="w-56 shrink-0">
          <div
            className="rounded-xl border"
            style={{ background: "var(--bg-card)", borderColor: "var(--border-default)" }}
          >
            <div
              className="px-4 py-3 text-sm font-semibold border-b"
              style={{ borderColor: "var(--border-default)", color: "var(--text-primary)" }}
            >
              产品列表
            </div>
            <div className="py-1">
              {products.map((p) => {
                const isActive = p.id === activeProductId;
                const isSelected = p.id === editingProductId;
                const isRenaming = p.id === renamingProductId;
                return (
                  <div key={p.id}>
                    <div
                      className="w-full text-left px-4 py-2.5 text-sm flex items-center justify-between hover:brightness-95 transition-colors"
                      style={{
                        background: isSelected ? "var(--bg-nav-active)" : "transparent",
                        color: isSelected ? "var(--text-nav-active)" : "var(--text-primary)",
                      }}
                    >
                      {isRenaming ? (
                        <div className="flex items-center gap-1 flex-1 min-w-0">
                          <input
                            type="text"
                            className="flex-1 min-w-0 px-1 py-0.5 text-sm rounded border"
                            style={{
                              borderColor: "var(--border-default)",
                              background: "var(--bg-input)",
                              color: "var(--text-primary)",
                            }}
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={async (e) => {
                              if (e.key === "Enter" && renameValue.trim()) {
                                await renameProduct(p.id, renameValue.trim());
                                setRenamingProductId("");
                                setRenameValue("");
                              }
                              if (e.key === "Escape") {
                                setRenamingProductId("");
                                setRenameValue("");
                              }
                            }}
                            autoFocus
                          />
                          <button
                            className="text-xs px-1 hover:brightness-90"
                            style={{ color: "var(--success)" }}
                            onClick={async () => {
                              if (renameValue.trim()) {
                                await renameProduct(p.id, renameValue.trim());
                                setRenamingProductId("");
                                setRenameValue("");
                              }
                            }}
                            title="确认"
                          >
                            &#10003;
                          </button>
                          <button
                            className="text-xs px-1 hover:brightness-90"
                            style={{ color: "var(--text-tertiary)" }}
                            onClick={() => {
                              setRenamingProductId("");
                              setRenameValue("");
                            }}
                            title="取消"
                          >
                            &#10005;
                          </button>
                        </div>
                      ) : (
                        <>
                          <button
                            className="truncate text-left flex-1 min-w-0"
                            style={{ color: "inherit" }}
                            onClick={() => handleSelectProduct(p.id)}
                          >
                            {p.name || p.id}
                          </button>
                          <span className="flex items-center gap-1 ml-1 shrink-0">
                            <button
                              className="text-xs opacity-50 hover:opacity-100 transition-opacity px-0.5"
                              style={{ color: "var(--text-tertiary)" }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setRenamingProductId(p.id);
                                setRenameValue(p.name || p.id);
                              }}
                              title="重命名"
                            >
                              &#9998;
                            </button>
                            {isActive ? (
                              <span
                                className="text-xs px-1.5 py-0.5 rounded"
                                style={{
                                  background: "var(--accent)",
                                  color: "var(--text-inverse)",
                                }}
                              >
                                当前活跃
                              </span>
                            ) : (
                              <button
                                className="text-xs opacity-50 hover:opacity-100 hover:text-[var(--danger)] transition-all px-0.5"
                                style={{ color: "var(--text-tertiary)" }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setDeleteConfirmId(p.id);
                                }}
                                title="删除"
                              >
                                &#128465;
                              </button>
                            )}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <div
              className="px-4 py-2 border-t"
              style={{ borderColor: "var(--border-default)" }}
            >
              <button
                className="text-xs w-full text-center py-1 rounded hover:brightness-95 transition-colors"
                style={{ color: "var(--accent)" }}
                onClick={() => setShowNewForm(true)}
              >
                + 新建产品
              </button>
            </div>
          </div>
        </div>

        {/* Config form */}
        <div className="flex-1 min-w-0">
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
                      描述脚本生成的场景方向，如：产品展示、制作过程、成品呈现
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
                      描述素材检索的方向，如：产品近景、细节处理、使用场景
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
            {isEditingActive && (
              <button
                className="px-6 py-3 font-medium rounded-xl hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                style={{ background: "var(--bg-page)", color: "var(--text-primary)" }}
                onClick={handleReset}
                disabled={saving}
              >
                重置为默认值
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Delete confirmation dialog */}
      {deleteConfirmId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,0.4)" }}
          onClick={() => setDeleteConfirmId("")}
        >
          <div
            className="rounded-xl border p-6 max-w-sm w-full mx-4"
            style={{ background: "var(--bg-card)", borderColor: "var(--border-default)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
              确认删除产品
            </h3>
            <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>
              删除后该产品的配置将被移除，但素材文件不会受影响。
              {deleteConfirmId === activeProductId && " 当前活跃产品将被删除，系统将自动切换到下一个产品。"}
            </p>
            <div className="flex gap-3 justify-end">
              <button
                className="px-4 py-2 text-sm font-medium rounded-lg hover:brightness-95 transition-colors"
                style={{ background: "var(--bg-page)", color: "var(--text-primary)" }}
                onClick={() => setDeleteConfirmId("")}
              >
                取消
              </button>
              <button
                className="px-4 py-2 text-sm font-medium rounded-lg hover:brightness-110 transition-colors"
                style={{ background: "var(--danger)", color: "#fff" }}
                onClick={async () => {
                  await deleteProduct(deleteConfirmId);
                  // If the deleted product was being edited, reload config
                  if (editingProductId === deleteConfirmId) {
                    setEditingProductId("");
                    setConfig(DEFAULT_CONFIG);
                  }
                  setDeleteConfirmId("");
                }}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
