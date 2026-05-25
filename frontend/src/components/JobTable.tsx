import { useNavigate } from "react-router-dom";
import type { JobSummary } from "../types";
import StatusBadge from "./StatusBadge";

interface Props {
  jobs: JobSummary[];
  onRetry: (jobId: string) => void;
}

export default function JobTable({ jobs, onRetry }: Props) {
  const navigate = useNavigate();

  if (jobs.length === 0) {
    return <p className="text-sm text-[#59636e] py-4">暂无 Job，创建一个开始吧</p>;
  }

  return (
    <table className="w-full border-collapse text-[13px]">
      <thead>
        <tr className="border-b border-[#393f46] text-left text-[#59636e]">
          <th className="py-2 px-2 font-medium">Job ID</th>
          <th className="py-2 px-2 font-medium">产品</th>
          <th className="py-2 px-2 font-medium">状态</th>
          <th className="py-2 px-2 font-medium">进度</th>
          <th className="py-2 px-2 font-medium">操作</th>
        </tr>
      </thead>
      <tbody>
        {jobs.map((j) => (
          <tr key={j.job_id} className="border-b border-[#eff2f5] hover:bg-gray-50">
            <td className="py-2.5 px-2 font-mono text-xs">{j.job_id}</td>
            <td className="py-2.5 px-2">{j.product}</td>
            <td className="py-2.5 px-2">
              <StatusBadge phase={j.phase} />
            </td>
            <td className="py-2.5 px-2 text-[#59636e]">
              {j.phase_index > 0 ? `${j.phase_index}/${j.phase_total}` : "\u2014"}
            </td>
            <td className="py-2.5 px-2">
              {j.phase === "failed" ? (
                <button
                  className="text-[#0969da] hover:underline text-xs"
                  onClick={() => onRetry(j.job_id)}
                >
                  重试 &#8634;
                </button>
              ) : (
                <button
                  className="text-[#0969da] hover:underline text-xs"
                  onClick={() => navigate(`/jobs/${j.job_id}`)}
                >
                  查看 &rarr;
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
