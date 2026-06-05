import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { JobSummary } from "../types";
import StatusBadge from "./StatusBadge";

interface Props {
  jobs: JobSummary[];
  onRetry: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  onRename?: (jobId: string, name: string) => Promise<void>;
}

export default function JobTable({ jobs, onRetry, onDelete, onRename }: Props) {
  const navigate = useNavigate();

  if (jobs.length === 0) {
    return <p className="text-sm text-[#59636e] py-4">暂无 Job，创建一个开始吧</p>;
  }

  return (
    <table className="w-full border-collapse text-[13px]">
      <thead>
        <tr className="border-b border-[#393f46] text-left text-[#59636e]">
          <th className="py-2 px-2 font-medium">Job ID</th>
          <th className="py-2 px-2 font-medium">名称</th>
          <th className="py-2 px-2 font-medium">产品</th>
          <th className="py-2 px-2 font-medium">状态</th>
          <th className="py-2 px-2 font-medium">进度</th>
          <th className="py-2 px-2 font-medium">操作</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((j) => (
          <NameRow key={j.job_id} job={j} onRename={onRename} onRetry={onRetry} onDelete={onDelete} navigate={navigate} />
        ))}
      </tbody>
    </table>
  );
}

function NameRow({ job, onRename, onRetry, onDelete, navigate }: {
  job: JobSummary;
  onRename?: (jobId: string, name: string) => Promise<void>;
  onRetry: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  navigate: ReturnType<typeof useNavigate>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(job.name || job.product);

  const displayName = job.name || job.product;

  const commit = async () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== displayName && onRename) {
      await onRename(job.job_id, trimmed);
    }
    setEditing(false);
    setDraft(job.name || job.product);
  };

  return (
    <tr className="border-b border-[#eff2f5] hover:bg-gray-50">
      <td className="py-2.5 px-2 font-mono text-xs">{job.job_id}</td>
      <td className="py-2.5 px-2">
        {editing ? (
          <input
            type="text"
            className="border rounded px-1.5 py-0.5 text-xs w-32"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") { setEditing(false); setDraft(job.name || job.product); }
            }}
            autoFocus
          />
        ) : (
          <span
            className="cursor-pointer hover:text-[#0969da]"
            title="双击编辑名称"
            onDoubleClick={() => { setEditing(true); setDraft(job.name || job.product); }}
          >
            {displayName}
          </span>
        )}
      </td>
      <td className="py-2.5 px-2">{job.product}</td>
      <td className="py-2.5 px-2">
        <StatusBadge phase={job.phase} />
      </td>
      <td className="py-2.5 px-2 text-[#59636e]">
        {job.phase_index > 0 ? `${job.phase_index}/${job.phase_total}` : "—"}
      </td>
      <td className="py-2.5 px-2 flex gap-2 items-center">
        {job.phase === "failed" ? (
          <button
            className="text-[#0969da] hover:underline text-xs"
            onClick={() => onRetry(job.job_id)}
          >
            重试 &#8634;
          </button>
        ) : (
          <button
            className="text-[#0969da] hover:underline text-xs"
            onClick={() => navigate(`/jobs/${job.job_id}`)}
          >
            查看 &rarr;
          </button>
        )}
        <button
          className="text-[#cf222e] hover:underline text-xs"
          onClick={() => onDelete(job.job_id)}
        >
          删除
        </button>
      </td>
    </tr>
  );
}
