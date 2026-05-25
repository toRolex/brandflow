import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Project } from "../types";

export default function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [newName, setNewName] = useState("");
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
            className="bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
            onClick={create}
          >
            创建项目
          </button>
        </div>
      </div>

      {projects.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <div className="text-4xl mb-4">📂</div>
          <p>暂无项目，创建一个开始吧</p>
        </div>
      ) : (
        <div className="border rounded-xl overflow-hidden">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-gray-50 border-b text-left text-gray-500">
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
                    <button
                      className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                      onClick={() => navigate(`/projects/${p.id}`)}
                    >
                      打开 →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
