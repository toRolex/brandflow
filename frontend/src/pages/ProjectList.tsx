import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Project } from "../types";

export default function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [newName, setNewName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const navigate = useNavigate();

  const load = () => {
    api.listProjects().then(setProjects).catch(() => setProjects([]));
  };

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!newName.trim()) return;
    try {
      const p = await api.createProject(newName.trim());
      setNewName("");
      navigate(`/projects/${p.id}`);
    } catch {
      // silently fail
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.deleteProject(deleteTarget.id);
      setDeleteTarget(null);
      load();
    } catch {
      // silently fail
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">项目列表</h1>
        <div className="flex gap-2">
          <input
            className="border rounded-lg px-3 py-2 text-sm w-48"
            placeholder="新项目名称"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <button
            className="bg-[#d1242f] text-white px-4 py-2 rounded-lg text-sm font-semibold hover:brightness-110 transition-all"
            onClick={create}
          >
            创建项目
          </button>
        </div>
      </div>

      {projects.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <div className="text-5xl mb-4">📂</div>
          <p>暂无项目，创建一个开始吧</p>
        </div>
      ) : (
        <div className="border rounded-xl overflow-hidden">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-[#393f46] text-left text-[#59636e]">
                <th className="py-3 px-4 font-medium">项目名称</th>
                <th className="py-3 px-4 font-medium">状态</th>
                <th className="py-3 px-4 font-medium">Jobs</th>
                <th className="py-3 px-4 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id} className="border-b hover:bg-gray-50 transition-colors">
                  <td className="py-3 px-4 font-medium">{p.name || p.id}</td>
                  <td className="py-3 px-4 text-gray-500">{p.status}</td>
                  <td className="py-3 px-4 text-gray-500">{p.job_count}</td>
                  <td className="py-3 px-4">
                    <div className="flex gap-2">
                      <button
                        className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        onClick={() => navigate(`/projects/${p.id}`)}
                      >
                        打开 →
                      </button>
                      <button
                        className="text-red-600 hover:text-red-800 text-sm font-medium"
                        onClick={() => setDeleteTarget(p)}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-bold mb-2">确认删除</h3>
            <p className="text-gray-600 mb-6">
              确定要删除项目「{deleteTarget.name || deleteTarget.id}」吗？此操作不可撤销。
            </p>
            <div className="flex justify-end gap-3">
              <button
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
                onClick={() => setDeleteTarget(null)}
              >
                取消
              </button>
              <button
                className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700"
                onClick={confirmDelete}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
