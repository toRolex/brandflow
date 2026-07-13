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

/** Generate a stable machine-readable id from a category name.
 *  Lowercase, replace spaces with underscores, strip non-alphanumeric chars.
 *  Falls back to a timestamp-based id for pure-Chinese names. */
function generateCategoryId(name: string): string {
  const cleaned = name.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
  if (!cleaned.replace(/_/g, "")) {
    return `cat_${Date.now().toString(36)}`;
  }
  return cleaned;
}

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
      // Edit existing category — preserve existing id
      const existingId = categories[editingIndex]?.id;
      const updatedCategories = categories.map((c, i) =>
        i === editingIndex
          ? {
              id: existingId || generateCategoryId(formData.name.trim()),
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
      // Add new category — auto-generate id
      const newCategory: CategoryConfig = {
        id: generateCategoryId(formData.name.trim()),
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
      id: generateCategoryId(s.label),
      name: s.label,
      description: s.description,
      vision_prompt: s.vision_prompt,
    }));

    // Merge with existing categories, avoid duplicates by id then by name
    const existingIds = new Set(categories.map((c) => c.id));
    const existingNames = new Set(categories.map((c) => c.name));
    const merged = [
      ...categories,
      ...newCategories.filter((c) => !existingIds.has(c.id) && !existingNames.has(c.name)),
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
    return <div className="text-center py-12 text-[var(--text-tertiary)]">加载配置中...</div>;
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">素材分类</h1>

      {loadError && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm bg-[var(--danger-bg)] border border-[var(--danger-border)] text-[var(--danger)]">
          {loadError}
        </div>
      )}

      {saveMsg && (
        <div
          className={`mb-4 px-4 py-3 rounded-lg text-sm ${
            saveMsg.includes("失败")
              ? "bg-[var(--danger-bg)] border border-[var(--danger-border)] text-[var(--danger)]"
              : "bg-[var(--success-bg)] border border-[var(--success-border)] text-[var(--success)]"
          }`}
        >
          {saveMsg}
        </div>
      )}

      {/* AI Suggestion Button */}
      <div className="mb-6">
        <button
          className="px-4 py-2 bg-[var(--accent)] text-[var(--text-inverse)] font-medium rounded-xl hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
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
                className="flex items-start gap-3 p-3 bg-[var(--bg-card)] rounded-lg border border-[var(--border-default)] cursor-pointer hover:border-[var(--accent)] transition-colors"
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={pendingSuggestionNames.has(s.label)}
                  onChange={() => toggleSuggestion(s.label)}
                />
                <div>
                  <div className="font-medium text-sm">{s.label}</div>
                  <div className="text-xs text-[var(--text-secondary)]">{s.description}</div>
                  <div className="text-xs text-[var(--text-tertiary)] mt-0.5 font-mono">{s.vision_prompt}</div>
                </div>
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              className="px-4 py-2 bg-[var(--accent)] text-[var(--text-inverse)] rounded-lg text-sm hover:brightness-110 disabled:opacity-50 transition-colors"
              onClick={confirmSuggestions}
              disabled={saving || pendingSuggestionNames.size === 0}
            >
              确认添加
            </button>
            <button
              className="px-4 py-2 bg-[var(--bg-table-head)] text-[var(--text-primary)] rounded-lg text-sm hover:brightness-95 transition-colors"
              onClick={cancelSuggestions}
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* Category List */}
      <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border-default)] overflow-hidden">
        {categories.length === 0 ? (
          <div className="text-center py-12 text-[var(--text-tertiary)]">暂无分类</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-[var(--bg-table-head)] border-b border-[var(--border-default)]">
                <th className="text-left px-5 py-3 text-xs font-medium text-[var(--text-tertiary)]">分类名称</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-[var(--text-tertiary)]">描述</th>
                <th className="text-left px-5 py-3 text-xs font-medium text-[var(--text-tertiary)]">Vision Prompt</th>
                <th className="text-right px-5 py-3 text-xs font-medium text-[var(--text-tertiary)]">操作</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((cat, i) => (
                <tr key={cat.id} className="border-b border-[var(--border-subtle)] last:border-0">
                  <td className="px-5 py-4 text-sm font-medium">{cat.name}</td>
                  <td className="px-5 py-4 text-sm text-[var(--text-secondary)]">{cat.description}</td>
                  <td className="px-5 py-4 text-sm text-[var(--text-tertiary)] font-mono">{cat.vision_prompt}</td>
                  <td className="px-5 py-4 text-right">
                    <button
                      className="text-[var(--accent)] hover:underline text-sm mr-3 disabled:opacity-50 transition-colors"
                      onClick={() => handleEdit(i)}
                      disabled={saving}
                    >
                      编辑
                    </button>
                    <button
                      className="text-[var(--danger)] hover:underline text-sm disabled:opacity-50 transition-colors"
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
        className="mt-4 px-4 py-2 bg-[var(--accent)] text-[var(--text-inverse)] font-medium rounded-xl hover:brightness-110 transition-colors text-sm"
        onClick={() => { setShowForm(true); setEditingIndex(null); setFormData(EMPTY_FORM); }}
      >
        新增分类
      </button>

      {/* Add Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-[var(--bg-card)] rounded-2xl p-6 w-full max-w-md mx-4 shadow-xl">
            <h3 className="text-lg font-semibold mb-4">{editingIndex !== null ? "编辑分类" : "新增分类"}</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                  分类名称 <span className="text-[var(--danger)]">*</span>
                </label>
                <input
                  type="text"
                  className={`w-full px-4 py-2 border rounded-lg text-sm ${
                    formErrors.name ? "border-[var(--danger-border)] bg-[var(--danger-bg)]" : "border-[var(--border-default)]"
                  }`}
                  placeholder="分类名称"
                  value={formData.name}
                  onChange={(e) => {
                    setFormData((prev) => ({ ...prev, name: e.target.value }));
                    if (formErrors.name) setFormErrors({});
                  }}
                />
                {formErrors.name && (
                  <p className="mt-1 text-xs text-[var(--danger)]">{formErrors.name}</p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">描述</label>
                <input
                  type="text"
                  className="w-full px-4 py-2 border border-[var(--border-default)] rounded-lg text-sm"
                  placeholder="分类描述"
                  value={formData.description}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, description: e.target.value }))
                  }
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">Vision Prompt</label>
                <input
                  type="text"
                  className="w-full px-4 py-2 border border-[var(--border-default)] rounded-lg text-sm"
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
                className="px-4 py-2 bg-[var(--bg-table-head)] text-[var(--text-primary)] rounded-lg text-sm hover:brightness-95 transition-colors"
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
                className="px-4 py-2 bg-[var(--accent)] text-[var(--text-inverse)] rounded-lg text-sm hover:brightness-110 disabled:opacity-50 transition-colors"
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
