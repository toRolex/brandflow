import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ScriptTemplate, TemplateSlot, TemplateVariable, SlotType, VariableSource } from "../types";

const SLOT_TYPE_OPTIONS: { value: SlotType; label: string }[] = [
  { value: "hook", label: "开头钩子" },
  { value: "selling_point", label: "核心卖点" },
  { value: "usage_scene", label: "使用场景" },
  { value: "call_to_action", label: "行动号召" },
];

const VARIABLE_SOURCE_OPTIONS: { value: VariableSource; label: string }[] = [
  { value: "manual", label: "手动输入" },
  { value: "product_config", label: "产品配置自动填充" },
  { value: "knowledge_base", label: "知识库" },
];

const EMPTY_SLOT: TemplateSlot = { type: "hook", label: "", required: false, max_length: 200, hint: "" };
const EMPTY_VARIABLE: TemplateVariable = { name: "", label: "", source: "manual" };

function emptyTemplate(): ScriptTemplate {
  return { id: "", name: "", description: "", slots: [], variables: [], default_config_override: {} };
}

export default function ScriptTemplateEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === "new" || !id;

  const [template, setTemplate] = useState<ScriptTemplate>(emptyTemplate);
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  // Preview state
  const [previewSlotContents, setPreviewSlotContents] = useState<Record<string, string>>({});
  const [previewVariableValues, setPreviewVariableValues] = useState<Record<string, string>>({});
  const [previewResult, setPreviewResult] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const load = useCallback(async () => {
    if (!id || isNew) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getTemplate(id);
      setTemplate(data);
      // Initialize preview with empty values
      const slotContents: Record<string, string> = {};
      data.slots.forEach((s) => { slotContents[s.label] = ""; });
      setPreviewSlotContents(slotContents);
      const varValues: Record<string, string> = {};
      data.variables.forEach((v) => { varValues[v.name] = ""; });
      setPreviewVariableValues(varValues);
    } catch {
      setError("加载模板失败");
    }
    setLoading(false);
  }, [id, isNew]);

  useEffect(() => {
    load();
  }, [load]);

  const validate = (): boolean => {
    if (!template.name.trim()) {
      setError("模板名称不能为空");
      return false;
    }
    return true;
  };

  const handleSave = async () => {
    if (!validate()) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      let result: ScriptTemplate;
      if (isNew) {
        result = await api.createTemplate(template);
      } else if (id) {
        result = await api.updateTemplate(id, template);
      } else {
        return;
      }
      setTemplate(result);
      setSaveMsg("模板已保存");
      // If new, navigate to edit url
      if (isNew && result.id) {
        navigate(`/system/config/templates/${result.id}`, { replace: true });
      }
      setTimeout(() => setSaveMsg(null), 3000);
    } catch {
      setSaveMsg("保存失败");
    }
    setSaving(false);
  };

  const handlePreview = async () => {
    if (!id || isNew) return;
    setPreviewLoading(true);
    setPreviewResult(null);
    try {
      const res = await api.previewTemplate(id, previewSlotContents, previewVariableValues);
      setPreviewResult(res.rendered_script);
    } catch {
      setPreviewResult("预览生成失败");
    }
    setPreviewLoading(false);
  };

  if (loading) {
    return <div className="text-center py-12 text-gray-400">加载模板中...</div>;
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <button
          className="text-gray-500 hover:text-gray-700 text-sm"
          onClick={() => navigate("/system/config/templates")}
        >
          &larr; 返回模板列表
        </button>
        <span className="text-gray-300">|</span>
        <h1 className="text-xl font-bold">
          {isNew ? "新建脚本模板" : "编辑脚本模板"}
        </h1>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm bg-red-50 border border-red-200 text-red-700">
          {error}
        </div>
      )}
      {saveMsg && (
        <div className={`mb-4 px-4 py-3 rounded-lg text-sm ${
          saveMsg.includes("失败")
            ? "bg-red-50 border border-red-200 text-red-700"
            : "bg-green-50 border border-green-200 text-green-700"
        }`}>
          {saveMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Metadata */}
        <div className="lg:col-span-2 space-y-6">
          {/* Basic Info */}
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">基本信息</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  模板名称 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm"
                  placeholder="输入模板名称"
                  value={template.name}
                  onChange={(e) => setTemplate({ ...template, name: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">描述</label>
                <textarea
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg resize-none text-sm"
                  rows={3}
                  placeholder="模板描述"
                  value={template.description}
                  onChange={(e) => setTemplate({ ...template, description: e.target.value })}
                />
              </div>
            </div>
          </section>

          {/* Slots */}
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">脚本片段</h2>
              <button
                className="px-3 py-1.5 bg-[#0969da] text-white text-xs rounded-lg hover:brightness-110"
                onClick={() =>
                  setTemplate({
                    ...template,
                    slots: [...template.slots, { ...EMPTY_SLOT }],
                  })
                }
              >
                添加片段
              </button>
            </div>
            <div className="space-y-4">
              {template.slots.length === 0 && (
                <p className="text-gray-400 text-sm">暂无片段，点击"添加片段"创建</p>
              )}
              {template.slots.map((slot, idx) => (
                <div key={idx} className="border border-gray-200 rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-400 font-mono">片段 #{idx + 1}</span>
                    <button
                      className="text-xs text-red-500 hover:text-red-700"
                      onClick={() => {
                        const slots = template.slots.filter((_, i) => i !== idx);
                        setTemplate({ ...template, slots });
                      }}
                    >
                      删除
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">类型</label>
                      <select
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
                        value={slot.type}
                        onChange={(e) => {
                          const slots = [...template.slots];
                          slots[idx] = { ...slots[idx], type: e.target.value as SlotType };
                          setTemplate({ ...template, slots });
                        }}
                      >
                        {SLOT_TYPE_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">标签</label>
                      <input
                        type="text"
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        placeholder="如：开头钩子"
                        value={slot.label}
                        onChange={(e) => {
                          const slots = [...template.slots];
                          slots[idx] = { ...slots[idx], label: e.target.value };
                          setTemplate({ ...template, slots });
                        }}
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <label className="flex items-center gap-2 text-xs text-gray-500">
                      <input
                        type="checkbox"
                        checked={slot.required}
                        onChange={(e) => {
                          const slots = [...template.slots];
                          slots[idx] = { ...slots[idx], required: e.target.checked };
                          setTemplate({ ...template, slots });
                        }}
                      />
                      必填
                    </label>
                    <div className="flex-1">
                      <label className="block text-xs text-gray-500 mb-1">最大字数</label>
                      <input
                        type="number"
                        className="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        value={slot.max_length}
                        onChange={(e) => {
                          const slots = [...template.slots];
                          slots[idx] = { ...slots[idx], max_length: parseInt(e.target.value) || 200 };
                          setTemplate({ ...template, slots });
                        }}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">提示</label>
                    <input
                      type="text"
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                      placeholder="填写提示"
                      value={slot.hint}
                      onChange={(e) => {
                        const slots = [...template.slots];
                        slots[idx] = { ...slots[idx], hint: e.target.value };
                        setTemplate({ ...template, slots });
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Variables */}
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">变量</h2>
              <button
                className="px-3 py-1.5 bg-[#0969da] text-white text-xs rounded-lg hover:brightness-110"
                onClick={() =>
                  setTemplate({
                    ...template,
                    variables: [...template.variables, { ...EMPTY_VARIABLE }],
                  })
                }
              >
                添加变量
              </button>
            </div>
            <div className="space-y-4">
              {template.variables.length === 0 && (
                <p className="text-gray-400 text-sm">暂无变量，点击"添加变量"创建</p>
              )}
              {template.variables.map((v, idx) => (
                <div key={idx} className="border border-gray-200 rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-400 font-mono">变量 #{idx + 1}</span>
                    <button
                      className="text-xs text-red-500 hover:text-red-700"
                      onClick={() => {
                        const variables = template.variables.filter((_, i) => i !== idx);
                        setTemplate({ ...template, variables });
                      }}
                    >
                      删除
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">变量名</label>
                      <input
                        type="text"
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        placeholder="如：product_name"
                        value={v.name}
                        onChange={(e) => {
                          const variables = [...template.variables];
                          variables[idx] = { ...variables[idx], name: e.target.value };
                          setTemplate({ ...template, variables });
                        }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">标签</label>
                      <input
                        type="text"
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                        placeholder="如：产品名"
                        value={v.label}
                        onChange={(e) => {
                          const variables = [...template.variables];
                          variables[idx] = { ...variables[idx], label: e.target.value };
                          setTemplate({ ...template, variables });
                        }}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">来源</label>
                    <select
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
                      value={v.source}
                      onChange={(e) => {
                        const variables = [...template.variables];
                        variables[idx] = { ...variables[idx], source: e.target.value as VariableSource };
                        setTemplate({ ...template, variables });
                      }}
                    >
                      {VARIABLE_SOURCE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* Right: Preview */}
        <div className="space-y-6">
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-lg font-semibold mb-4">预览</h2>
            {isNew ? (
              <p className="text-gray-400 text-sm">保存模板后可预览</p>
            ) : (
              <div className="space-y-4">
                {template.slots.map((slot, idx) => (
                  <div key={idx}>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      {slot.label || `片段 #${idx + 1}`}
                      {slot.required && <span className="text-red-500 ml-1">*</span>}
                    </label>
                    <textarea
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none"
                      rows={2}
                      placeholder={slot.hint || `输入${slot.label}内容`}
                      value={previewSlotContents[slot.label] || ""}
                      onChange={(e) =>
                        setPreviewSlotContents({ ...previewSlotContents, [slot.label]: e.target.value })
                      }
                    />
                  </div>
                ))}
                {template.variables.map((v, idx) => (
                  <div key={idx}>
                    <label className="block text-xs font-medium text-gray-500 mb-1">
                      {v.label || v.name}
                      <span className="text-gray-400 ml-1">
                        ({VARIABLE_SOURCE_OPTIONS.find((o) => o.value === v.source)?.label || v.source})
                      </span>
                    </label>
                    <input
                      type="text"
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                      placeholder={`输入${v.label || v.name}`}
                      value={previewVariableValues[v.name] || ""}
                      onChange={(e) =>
                        setPreviewVariableValues({ ...previewVariableValues, [v.name]: e.target.value })
                      }
                    />
                  </div>
                ))}
                <button
                  className="w-full px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 disabled:opacity-50"
                  onClick={handlePreview}
                  disabled={previewLoading}
                >
                  {previewLoading ? "生成中..." : "生成预览"}
                </button>
                {previewResult !== null && (
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">预览结果</label>
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm whitespace-pre-wrap">
                      {previewResult}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      </div>

      {/* Save button */}
      <div className="flex items-center gap-4 mt-6">
        <button
          className="px-6 py-3 bg-[#0969da] text-white font-medium rounded-xl hover:brightness-110 disabled:opacity-50 transition-colors"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? "保存中..." : "保存模板"}
        </button>
      </div>
    </div>
  );
}
