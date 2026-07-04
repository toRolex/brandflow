import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ScriptTemplate } from "../types";

export default function ScriptTemplateList() {
  const [templates, setTemplates] = useState<ScriptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listTemplates();
      setTemplates(data);
    } catch {
      setError("加载模板列表失败");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = async (id: string) => {
    try {
      await api.deleteTemplate(id);
      load();
    } catch {
      setError("删除模板失败");
    }
  };

  if (loading) {
    return <div className="text-center py-12 text-gray-400">加载中...</div>;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">脚本模板</h1>
        <Link
          to="/system/config/templates/new"
          className="px-4 py-2 bg-[#0969da] text-white text-sm font-medium rounded-xl hover:brightness-110 transition-colors"
        >
          新建模板
        </Link>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg text-sm bg-red-50 border border-red-200 text-red-700">
          {error}
        </div>
      )}

      {templates.length === 0 ? (
        <div className="text-center py-16 bg-gray-50 rounded-xl border border-gray-200">
          <p className="text-gray-400 mb-2">暂无脚本模板</p>
          <p className="text-gray-400 text-sm">
            点击"新建模板"创建第一个脚本模板
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((tmpl) => (
            <div
              key={tmpl.id}
              className="bg-white rounded-xl border border-gray-200 p-5 flex flex-col"
            >
              <Link
                to={`/system/config/templates/${tmpl.id}`}
                className="text-lg font-semibold text-[#0969da] hover:underline mb-2"
              >
                {tmpl.name}
              </Link>
              <p className="text-sm text-gray-500 mb-3 flex-1">
                {tmpl.description || "无描述"}
              </p>
              <div className="flex items-center justify-between text-xs text-gray-400 mb-4">
                <span>{tmpl.slots.length} 个片段</span>
                <span>{tmpl.variables.length} 个变量</span>
              </div>
              <div className="flex gap-2">
                <Link
                  to={`/system/config/templates/${tmpl.id}`}
                  className="px-3 py-1.5 bg-gray-100 text-gray-700 text-xs rounded-lg hover:bg-gray-200 transition-colors"
                >
                  编辑
                </Link>
                <button
                  className="px-3 py-1.5 bg-red-50 text-red-600 text-xs rounded-lg hover:bg-red-100 transition-colors"
                  onClick={() => handleDelete(tmpl.id)}
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
