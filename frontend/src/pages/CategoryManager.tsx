import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import type { CategoryConfig, SuggestCategory, ProductConfig } from "../types";

interface FormData {
  name: string;
  description: string;
  vision_prompt: string;
}

interface FormErrors {
  name?: string;
}

const EMPTY_FORM: FormData = { name: "", description: "", vision_prompt: "" };

export default function CategoryManager() {
  const [config, setConfig] = useState<ProductConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState<FormData>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const [suggestions, setSuggestions] = useState<SuggestCategory[] | null>(null);
  const [pendingSuggestionNames, setPendingSuggestionNames] = useState<Set<string>>(new Set());
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await api.getProductConfig();
      setConfig(data);
    } catch {
      setLoadError("加载分类失败");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const categories = config?.categories ?? [];

  const validateForm = (): boolean => {
    const errors: FormErrors = {};
    if (!formData.name.trim()) {
      errors.name = "分类名称不能为空";
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleAddCategory = async () => {
    if (!validateForm()) return;
    if (!config) return;

    setSaving(true);
    setSaveMsg(null);

    if (editingIndex !== null) {
      // Edit existing category
      const updatedCategories = categories.map((c, i) =>
        i === editingIndex
          ? {
              name: formData.name.trim(),
              description: formData.description.trim(),
              vision_prompt: formData.vision_prompt.trim(),
            }
          : c
      );

      try {
        const updated = await api.saveProductConfig({
          ...config,
          categories: updatedCategories,
        });
        setConfig(updated);
        setShowForm(false);
        setFormData(EMPTY_FORM);
        setEditingIndex(null);
        setSaveMsg("分类已更新");
        setTimeout(() => setSaveMsg(null), 3000);
      } catch {
        setSaveMsg("保存失败");
      }
    } else {
      // Add new category
      const newCategory: CategoryConfig = {
        name: formData.name.trim(),
        description: formData.description.trim(),
        vision_prompt: formData.vision_prompt.trim(),
      };

      try {
        const updated = await api.saveProductConfig({
          ...config,
          categories: [...categories, newCategory],
        });
        setConfig(updated);
        setShowForm(false);
        setFormData(EMPTY_FORM);
        setSaveMsg("分类已保存");
        setTimeout(() => setSaveMsg(null), 3000);
      } catch {
        setSaveMsg("保存失败");
      }
    }
    setSaving(false);
  };

  const handleEdit = (index: number) => {
    const cat = categories[index];
    setFormData({
      name: cat.name,
      description: cat.description,
      vision_prompt: cat.vision_prompt,
    });
    setEditingIndex(index);
    setFormErrors({});
    setShowForm(true);
  };

  const handleDelete = async (index: number) => {
    if (!config) return;
    setSaving(true);
    setSaveMsg(null);
    const updatedCategories = categories.filter((_, i) => i !== index);
    try {
      const updated = await api.saveProductConfig({
        ...config,
        categories: updatedCategories,
      });
      setConfig(updated);
      setSaveMsg("分类已删除");
      setTimeout(() => setSaveMsg(null), 3000);
    } catch {
      setSaveMsg("保存失败");
    }
    setSaving(false);
  };

  const handleSuggest = async () => {
    if (!config) return;
    setSuggestLoading(true);
    setSuggestions(null);
    try {
      const result = await api.suggestCategories();
      setSuggestions(result.suggestions);
      // All suggestions checked by default
      setPendingSuggestionNames(new Set(result.suggestions.map((s) => s.label)));
    } catch {
      setSaveMsg("获取 AI 建议失败");
      setTimeout(() => setSaveMsg(null), 3000);
    }
    setSuggestLoading(false);
  };

  const toggleSuggestion = (label: string) => {
    setPendingSuggestionNames((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  const confirmSuggestions = async () => {
    if (!config || !suggestions) return;
    setSaving(true);
    setSaveMsg(null);

    const checked = suggestions.filter((s) => pendingSuggestionNames.has(s.label));
    const newCategories: CategoryConfig[] = checked.map((s) => ({
      name: s.label,
      description: s.description,
      vision_prompt: s.vision_prompt,
    }));

    // Merge with existing categories, avoid duplicates by name
    const existingNames = new Set(categories.map((c) => c.name));
    const merged = [
      ...categories,
      ...newCategories.filter((c) => !existingNames.has(c.name)),
    ];

    try {
      const updated = await api.saveProductConfig({
        ...config,
        categories: merged,
      });
      setConfig(updated);
      setSuggestions(null);
      setSaveMsg("分类已更新");
      setTimeout(() => setSaveMsg(null), 3000);
    } catch {
      setSaveMsg("保存失败");
    }
    setSaving(false);
  };

  const cancelSuggestions = () => {
    setSuggestions(null);
    setPendingSuggestionNames(new Set());
  };

  if (loading) {
    return <div className="text-center py-12 text-gray-400">加载配置中...</div>;
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">素材分类</h1>

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

      {/* AI Suggestion Button */}
      <div className="mb-6">
        <button
          className="px-4 py-2 bg-purple-600 text-white font-medium rounded-xl hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
          onClick={handleSuggest}
          disabled={suggestLoading || saving}
        >
          {suggestLoading ? "获取建议中..." : "AI 建议"}
        </button>
      </div>

      {/* AI Suggestions Panel */}
      {suggestions && (
        <div className="mb-6 border rounded-xl p-5" style={{ background: "var(--bg-tag-blue)", borderColor: "var(--text-tag-blue)" }}>
          <h3 className="font-semibold mb-3" style={{ color: "var(--text-tag-blue)" }}>AI 分类建议</h3>
          <p className="text-xs mb-3" style={{ color: "var(--text-secondary)" }}>勾选需要添加的分类，确认后将合并到现有分类列表</p>
          <div className="space-y-2 mb-4">
            {suggestions.map((s) => (
              <label
                key={s.label}
                className="flex items-start gap-3 p-3 bg-white rounded-lg border border-purple-100 cursor-pointer hover:border-purple-300 transition-colors"
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={pendingSuggestionNames.has(s.label)}
                  onChange={() => toggleSuggestion(s.label)}
                />
                <div>
                  <div className="font-medium text-sm">{s.label}</div>
                  <div className="text-xs text-gray-500">{s.description}</div>
                  <div className="text-xs text-gray-400 mt-0.5 font-mono">{s.vision_prompt}</div>
                </div>
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700 disabled:opacity-50 transition-colors"
              onClick={confirmSuggestions}
              disabled={saving || pendingSuggestionNames.size === 0}
            >
              确认添加
            </button>
            <button
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition-colors"
              onClick={cancelSuggestions}
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* Category List */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {categories.length === 0 ? (
          <div className="text-center py-12 text-gray-400">暂无分类</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-5 py-3 text-xs font-medium text-gray-500">分类名称</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-gray-500">描述</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-gray-500">Vision Prompt</th>
                <th className="text-right px-5 py-3 text-xs font-medium text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((cat, i) => (
                <tr key={cat.name} className="border-b border-gray-100 last:border-0">
                  <td className="px-5 py-4 text-sm font-medium">{cat.name}</td>
                  <td className="px-5 py-4 text-sm text-gray-600">{cat.description}</td>
                  <td className="px-5 py-4 text-sm text-gray-500 font-mono">{cat.vision_prompt}</td>
                  <td className="px-5 py-4 text-right">
                    <button
                      className="text-[var(--accent)] hover:underline text-sm mr-3 disabled:opacity-50 transition-colors"
                      onClick={() => handleEdit(i)}
                      disabled={saving}
                    >
                      编辑
                    </button>
                    <button
                      className="text-red-500 hover:text-red-700 text-sm disabled:opacity-50 transition-colors"
                      onClick={() => handleDelete(i)}
                      disabled={saving}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Add Button */}
      <button
        className="mt-4 px-4 py-2 bg-[#0969da] text-white font-medium rounded-xl hover:bg-[#0969da] hover:brightness-110 transition-colors text-sm"
        onClick={() => { setShowForm(true); setEditingIndex(null); setFormData(EMPTY_FORM); }}
      >
        新增分类
      </button>

      {/* Add Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md mx-4 shadow-xl">
            <h3 className="text-lg font-semibold mb-4">{editingIndex !== null ? "编辑分类" : "新增分类"}</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  分类名称 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  className={`w-full px-4 py-2 border rounded-lg text-sm ${
                    formErrors.name ? "border-red-300 bg-red-50" : "border-gray-300"
                  }`}
                  placeholder="分类名称"
                  value={formData.name}
                  onChange={(e) => {
                    setFormData((prev) => ({ ...prev, name: e.target.value }));
                    if (formErrors.name) setFormErrors({});
                  }}
                />
                {formErrors.name && (
                  <p className="mt-1 text-xs text-red-600">{formErrors.name}</p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">描述</label>
                <input
                  type="text"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm"
                  placeholder="分类描述"
                  value={formData.description}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, description: e.target.value }))
                  }
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Vision Prompt</label>
                <input
                  type="text"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm"
                  placeholder="Vision prompt"
                  value={formData.vision_prompt}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, vision_prompt: e.target.value }))
                  }
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition-colors"
                onClick={() => {
                  setShowForm(false);
                  setFormData(EMPTY_FORM);
                  setFormErrors({});
                  setEditingIndex(null);
                }}
              >
                取消
              </button>
              <button
                className="px-4 py-2 bg-[#0969da] text-white rounded-lg text-sm hover:brightness-110 disabled:opacity-50 transition-colors"
                onClick={handleAddCategory}
                disabled={saving}
              >
                确认
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
