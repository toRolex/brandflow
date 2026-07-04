import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import type { ProductConfig } from "../types";

interface LocalQualityRules {
  word_count_min: number;
  word_count_max: number;
  product_name_count: number;
  brand_name_count: number;
  forbidden_words: string[];
  emoji_forbidden: boolean;
}

const DEFAULT_RULES: LocalQualityRules = {
  word_count_min: 150,
  word_count_max: 200,
  product_name_count: 1,
  brand_name_count: 1,
  forbidden_words: [],
  emoji_forbidden: true,
};

export default function QualityRulesForm() {
  const [config, setConfig] = useState<ProductConfig | null>(null);
  const [rules, setRules] = useState<LocalQualityRules>(DEFAULT_RULES);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [newWord, setNewWord] = useState("");
  const [showNewWordInput, setShowNewWordInput] = useState(false);
  const [newWordError, setNewWordError] = useState<string | null>(null);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await api.getProductConfig();
      setConfig(data);
      setRules({
        word_count_min: data.script.word_count_min ?? DEFAULT_RULES.word_count_min,
        word_count_max: data.script.word_count_max ?? DEFAULT_RULES.word_count_max,
        product_name_count: data.script.product_name_count ?? DEFAULT_RULES.product_name_count,
        brand_name_count: data.script.brand_name_count ?? DEFAULT_RULES.brand_name_count,
        forbidden_words: data.script.forbidden_words ?? DEFAULT_RULES.forbidden_words,
        emoji_forbidden: data.script.emoji_forbidden ?? DEFAULT_RULES.emoji_forbidden,
      });
    } catch {
      setLoadError("加载质检规则失败");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const updateRule = <K extends keyof LocalQualityRules>(
    field: K,
    value: LocalQualityRules[K]
  ) => {
    setRules((prev) => ({ ...prev, [field]: value }));
  };

  const validateWordCount = (): string | null => {
    if (rules.word_count_min > rules.word_count_max) {
      return "最小值不能大于最大值";
    }
    if (rules.word_count_min < 1) {
      return "最小值不能小于1";
    }
    return null;
  };

  const handleSave = async () => {
    if (!config) return;

    const countError = validateWordCount();
    if (countError) {
      setSaveMsg(countError);
      setTimeout(() => setSaveMsg(null), 3000);
      return;
    }

    setSaving(true);
    setSaveMsg(null);
    try {
      const updated = await api.saveProductConfig({
        ...config,
        script: {
          ...config.script,
          word_count_min: rules.word_count_min,
          word_count_max: rules.word_count_max,
          product_name_count: rules.product_name_count,
          brand_name_count: rules.brand_name_count,
          forbidden_words: rules.forbidden_words,
          emoji_forbidden: rules.emoji_forbidden,
        },
      });
      setConfig(updated);
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

  const addForbiddenWord = () => {
    if (!newWord.trim()) {
      setNewWordError("禁词不能为空");
      return;
    }
    if (rules.forbidden_words.includes(newWord.trim())) {
      setNewWordError("禁词已存在");
      return;
    }
    updateRule("forbidden_words", [...rules.forbidden_words, newWord.trim()]);
    setNewWord("");
    setShowNewWordInput(false);
    setNewWordError(null);
  };

  const removeForbiddenWord = (index: number) => {
    updateRule(
      "forbidden_words",
      rules.forbidden_words.filter((_, i) => i !== index)
    );
  };

  if (loading) {
    return <div className="text-center py-12 text-gray-400">加载配置中...</div>;
  }

  const wordCountError = validateWordCount();

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">质检规则</h1>

      {loadError && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm bg-red-50 border border-red-200 text-red-700">
          {loadError}
        </div>
      )}

      {saveMsg && (
        <div
          className={`mb-4 px-4 py-3 rounded-lg text-sm ${
            saveMsg.includes("失败") || wordCountError === saveMsg
              ? "bg-red-50 border border-red-200 text-red-700"
              : "bg-green-50 border border-green-200 text-green-700"
          }`}
        >
          {saveMsg}
        </div>
      )}

      <div className="space-y-6">
        {/* 字数范围 */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold mb-4">字数范围</h2>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-2">最小字数</label>
              <input
                type="number"
                className={`w-full px-4 py-2 border rounded-lg text-sm ${
                  wordCountError ? "border-red-300 bg-red-50" : "border-gray-300"
                }`}
                value={rules.word_count_min}
                onChange={(e) => updateRule("word_count_min", parseInt(e.target.value) || 0)}
                min={1}
              />
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-2">最大字数</label>
              <input
                type="number"
                className={`w-full px-4 py-2 border rounded-lg text-sm ${
                  wordCountError ? "border-red-300 bg-red-50" : "border-gray-300"
                }`}
                value={rules.word_count_max}
                onChange={(e) => updateRule("word_count_max", parseInt(e.target.value) || 0)}
                min={1}
              />
            </div>
          </div>
          {rules.word_count_min > 0 && rules.word_count_max > 0 && !wordCountError && (
            <p className="mt-2 text-xs text-gray-500">
              字数必须在 {rules.word_count_min}-{rules.word_count_max} 之间
            </p>
          )}
          {wordCountError && (
            <p className="mt-2 text-xs text-red-600">{wordCountError}</p>
          )}
        </section>

        {/* 强制包含词 */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold mb-4">强制包含词</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                产品名出现次数
              </label>
              <input
                type="number"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm"
                value={rules.product_name_count}
                onChange={(e) =>
                  updateRule("product_name_count", Math.max(0, parseInt(e.target.value) || 0))
                }
                min={0}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                品牌名出现次数
              </label>
              <input
                type="number"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm"
                value={rules.brand_name_count}
                onChange={(e) =>
                  updateRule("brand_name_count", Math.max(0, parseInt(e.target.value) || 0))
                }
                min={0}
              />
            </div>
          </div>
        </section>

        {/* 禁词管理 */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold mb-4">禁词管理</h2>
          <div className="flex flex-wrap gap-2 mb-3">
            {rules.forbidden_words.map((word, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-3 py-1 bg-red-50 border border-red-200 text-red-700 rounded-full text-sm"
              >
                {word}
                <button
                  className="text-red-400 hover:text-red-600 ml-1 text-xs"
                  onClick={() => removeForbiddenWord(i)}
                >
                  ×
                </button>
              </span>
            ))}
            {rules.forbidden_words.length === 0 && (
              <span className="text-xs text-gray-400">暂无禁词</span>
            )}
          </div>

          {showNewWordInput ? (
            <div className="flex items-center gap-2">
              <input
                type="text"
                className={`flex-1 px-3 py-2 border rounded-lg text-sm ${
                  newWordError ? "border-red-300 bg-red-50" : "border-gray-300"
                }`}
                placeholder="输入禁词"
                value={newWord}
                onChange={(e) => {
                  setNewWord(e.target.value);
                  if (newWordError) setNewWordError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") addForbiddenWord();
                }}
                autoFocus
              />
              <button
                className="px-3 py-2 bg-[#0969da] text-white rounded-lg text-sm hover:brightness-110 transition-colors"
                onClick={addForbiddenWord}
              >
                确认
              </button>
              <button
                className="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition-colors"
                onClick={() => {
                  setShowNewWordInput(false);
                  setNewWord("");
                  setNewWordError(null);
                }}
              >
                取消
              </button>
            </div>
          ) : (
            <button
              className="text-sm text-[#0969da] hover:text-blue-700 font-medium transition-colors"
              onClick={() => setShowNewWordInput(true)}
            >
              + 添加
            </button>
          )}
          {newWordError && (
            <p className="mt-1 text-xs text-red-600">{newWordError}</p>
          )}
        </section>

        {/* Emoji 开关 */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">禁止 Emoji</h2>
              <p className="text-xs text-gray-500 mt-1">开启后脚本中不允许出现 emoji 字符</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={rules.emoji_forbidden}
                onChange={(e) => updateRule("emoji_forbidden", e.target.checked)}
              />
              <div className="w-11 h-6 bg-gray-200 rounded-full peer peer-checked:bg-[#0969da] peer-focus:outline-none transition-colors after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full" />
            </label>
          </div>
        </section>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-4 mt-6">
        <button
          className="px-6 py-3 bg-[#0969da] text-white font-medium rounded-xl hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
          恢复默认
        </button>
      </div>
    </div>
  );
}
