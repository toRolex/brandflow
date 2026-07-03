import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
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

export default function ProductConfigForm() {
  const [config, setConfig] = useState<ProductConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

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
    // Clear error when user starts typing
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
    return <div className="text-center py-12 text-gray-400">加载配置中...</div>;
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">产品配置</h1>

      {loadError && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm bg-red-50 border border-red-200 text-red-700">
          {loadError}
        </div>
      )}

      {saveMsg && (
        <div
          className={`mb-4 px-4 py-3 rounded-lg text-sm ${
            saveMsg.includes("失败")
              ? "bg-red-50 border border-red-200 text-red-700"
              : "bg-green-50 border border-green-200 text-green-700"
          }`}
        >
          {saveMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-6">
          {/* 产品名 */}
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">基本信息</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  产品名 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  className={`w-full px-4 py-2 border rounded-lg text-sm ${
                    errors.default_name
                      ? "border-red-300 bg-red-50"
                      : "border-gray-300"
                  }`}
                  placeholder="输入产品名称"
                  value={config.default_name}
                  onChange={(e) => updateField("default_name", e.target.value)}
                />
                {errors.default_name && (
                  <p className="mt-1 text-xs text-red-600">{errors.default_name}</p>
                )}
                <p className="mt-1 text-xs text-gray-400">
                  用于脚本生成和素材检索的默认产品名
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  品牌名 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  className={`w-full px-4 py-2 border rounded-lg text-sm ${
                    errors.default_brand
                      ? "border-red-300 bg-red-50"
                      : "border-gray-300"
                  }`}
                  placeholder="输入品牌名称"
                  value={config.default_brand}
                  onChange={(e) => updateField("default_brand", e.target.value)}
                />
                {errors.default_brand && (
                  <p className="mt-1 text-xs text-red-600">{errors.default_brand}</p>
                )}
                <p className="mt-1 text-xs text-gray-400">
                  品牌名，用于脚本生成
                </p>
              </div>
            </div>
          </section>
        </div>

        <div className="space-y-6">
          {/* 场景描述 */}
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">内容配置</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  场景描述
                </label>
                <textarea
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none text-sm"
                  rows={3}
                  placeholder="描述视频场景内容"
                  value={config.script.scene}
                  onChange={(e) => updateScriptField("scene", e.target.value)}
                />
                <p className="mt-1 text-xs text-gray-400">
                  描述脚本生成的场景方向，如：食材展示、烹饪过程、成品呈现
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  素材描述
                </label>
                <textarea
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none text-sm"
                  rows={3}
                  placeholder="描述所需素材内容"
                  value={config.script.material}
                  onChange={(e) => updateScriptField("material", e.target.value)}
                />
                <p className="mt-1 text-xs text-gray-400">
                  描述素材检索的方向，如：食材近景、清洗处理、烹饪翻炒
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  系统提示词
                </label>
                <textarea
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none text-sm"
                  rows={4}
                  placeholder="系统提示词，LLM 生成脚本时的角色设定"
                  value={config.script.system_prompt}
                  onChange={(e) => updateScriptField("system_prompt", e.target.value)}
                />
                <p className="mt-1 text-xs text-gray-400">
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
          className="px-6 py-3 bg-[#0969da] text-white font-medium rounded-xl hover:bg-[#0969da] hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? "保存中..." : "保存配置"}
        </button>
        <button
          className="px-6 py-3 bg-gray-100 text-gray-700 font-medium rounded-xl hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          onClick={handleReset}
          disabled={saving}
        >
          重置为默认值
        </button>
      </div>
    </div>
  );
}
