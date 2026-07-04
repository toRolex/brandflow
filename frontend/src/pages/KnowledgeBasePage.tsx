// frontend/src/pages/KnowledgeBasePage.tsx
import { useEffect, useState, useRef } from "react";
import { api } from "../api/client";

interface Document { id: string; filename: string; source_type: string; item_count: number; }

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      const res = await api.listDocuments();
      setDocuments((res as { documents: Document[] }).documents || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await api.uploadKnowledge(file);
      fileRef.current!.value = "";
      await load();
    } catch { alert("上传失败"); }
    finally { setUploading(false); }
  };

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--text-primary)" }}>知识库</h2>
      <div className="border-2 border-dashed rounded-lg p-6 mb-6 text-center" style={{ borderColor: "var(--border-default)" }}>
        <p className="text-sm mb-2" style={{ color: "var(--text-secondary)" }}>上传 TXT、PDF 或 DOCX 文件，自动提取知识点</p>
        <input ref={fileRef} type="file" accept=".txt,.pdf,.docx" className="block mx-auto text-sm" />
        <button onClick={upload} disabled={uploading}
          className="mt-3 px-4 py-1.5 text-sm font-medium rounded-md text-white transition-colors disabled:opacity-50"
          style={{ background: "var(--btn-primary-bg)" }}>{uploading ? "上传中..." : "上传并解析"}</button>
      </div>
      {loading ? <p className="text-sm" style={{ color: "var(--text-secondary)" }}>加载中...</p>
      : documents.length === 0 ? <p className="text-sm" style={{ color: "var(--text-tertiary)" }}>暂无文档</p>
      : <div className="space-y-2">{documents.map(doc => (
        <div key={doc.id} className="border rounded-lg p-3" style={{ background: "var(--bg-card)", borderColor: "var(--border-default)" }}>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>{doc.filename}</span>
            <span className="text-xs" style={{ color: "var(--text-tertiary)" }}>{doc.item_count} 个知识点</span>
          </div>
        </div>
      ))}</div>}
    </div>
  );
}
