import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SceneFolder, SceneFolderFile } from "../types";
import ConfirmDialog from "./ConfirmDialog";

export default function SceneUpload() {
  const [folders, setFolders] = useState<SceneFolder[]>([]);
  const [folderFiles, setFolderFiles] = useState<Record<string, SceneFolderFile[]>>({});
  const [expandedFolder, setExpandedFolder] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<{
    folderName: string;
    fileName: string;
  } | null>(null);

  const loadFolders = async () => {
    try {
      const data = await api.getSceneFolders();
      setFolders(data.folders || []);
      setError("");
    } catch (e) {
      console.error("load scene folders failed", e);
      setError("加载场景文件夹失败");
    }
    setLoading(false);
  };

  const loadFolderFiles = async (folderName: string) => {
    try {
      const data = await api.getSceneFolderFiles(folderName);
      setFolderFiles((prev) => ({ ...prev, [folderName]: data.files || [] }));
    } catch (e) {
      console.error("load folder files failed", e);
    }
  };

  useEffect(() => {
    loadFolders();
  }, []);

  const handleToggleFolder = (name: string) => {
    if (expandedFolder === name) {
      setExpandedFolder(null);
    } else {
      setExpandedFolder(name);
      if (!folderFiles[name]) {
        loadFolderFiles(name);
      }
    }
  };

  const handleUpload = async (folderName: string) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "video/*";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      setUploading(folderName);
      try {
        await api.uploadSceneVideo(folderName, file);
        await loadFolderFiles(folderName);
        await loadFolders();
      } catch (e) {
        console.error("upload scene video failed", e);
        setError("上传场景视频失败");
      }
      setUploading(null);
    };
    input.click();
  };

  const handleDelete = async (folderName: string, fileName: string) => {
    setConfirmDelete({ folderName, fileName });
  };

  const executeDelete = async () => {
    if (!confirmDelete) return;
    const { folderName, fileName } = confirmDelete;
    setConfirmDelete(null);
    try {
      await api.deleteSceneFile(folderName, fileName);
      await loadFolderFiles(folderName);
      await loadFolders();
    } catch (e) {
      console.error("delete scene file failed", e);
      setError("删除场景文件失败");
    }
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (loading) {
    return <div className="text-center py-12 text-gray-400">加载中...</div>;
  }

  return (
    <div>
      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError("")} className="text-red-400 hover:text-red-600 text-lg leading-none">&times;</button>
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[15px] font-semibold">场景素材库</h3>
        <button
          className="text-xs border rounded px-3 py-1.5 hover:bg-gray-50 transition-colors"
          onClick={loadFolders}
        >
          刷新列表
        </button>
      </div>

      {folders.length === 0 ? (
        <div className="text-center py-12 text-gray-400 text-sm">
          暂无场景文件夹，请先通过接口创建场景文件夹并上传视频
        </div>
      ) : (
        <div className="space-y-3">
          {folders.map((folder) => {
            const isExpanded = expandedFolder === folder.name;
            const files = folderFiles[folder.name];

            return (
              <div key={folder.name} className="border rounded-xl bg-white overflow-hidden">
                {/* Folder header */}
                <div
                  className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => handleToggleFolder(folder.name)}
                >
                  <div className="flex items-center gap-3">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="var(--text-secondary)"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className={`transition-transform ${isExpanded ? "rotate-90" : ""}`}
                    >
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="20"
                      height="20"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="var(--color-alert-red)"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                    </svg>
                    <span className="text-sm font-medium">{folder.name}</span>
                    <span className="text-xs text-gray-400">
                      {folder.file_count} 个文件
                    </span>
                  </div>
                  <button
                    className="text-xs bg-[var(--btn-danger-bg)] text-white px-3 py-1.5 rounded-md hover:brightness-110 transition-all disabled:opacity-50 flex items-center gap-1.5"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleUpload(folder.name);
                    }}
                    disabled={uploading === folder.name}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    {uploading === folder.name ? "上传中..." : "上传视频"}
                  </button>
                </div>

                {/* Folder files (expanded) */}
                {isExpanded && (
                  <div className="border-t">
                    {!files ? (
                      <div className="px-4 py-3 text-xs text-gray-400">加载中...</div>
                    ) : files.length === 0 ? (
                      <div className="px-4 py-3 text-xs text-gray-400">暂无文件，请上传</div>
                    ) : (
                      <div className="divide-y">
                        {files.map((file) => (
                          <div
                            key={file.name}
                            className="flex items-center justify-between px-4 py-2.5 hover:bg-gray-50"
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
                              <span className="text-sm truncate">{file.name}</span>
                              <span className="text-xs text-gray-400 flex-shrink-0">
                                {formatSize(file.size_bytes)}
                              </span>
                            </div>
                            <button
                              className="text-xs text-[var(--color-alert-red)] hover:underline flex-shrink-0 ml-4"
                              onClick={() => handleDelete(folder.name, file.name)}
                            >
                              删除
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <ConfirmDialog
        isOpen={confirmDelete !== null}
        title="确认删除"
        message={`确认删除 ${confirmDelete?.fileName ?? ""}？此操作不可撤销。`}
        danger
        confirmLabel="删除"
        onConfirm={executeDelete}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
