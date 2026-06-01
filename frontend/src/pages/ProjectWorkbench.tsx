import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { JobSummary, ScheduleEntry } from "../types";
import FileDropzone from "../components/FileDropzone";
import JobTable from "../components/JobTable";
import ScheduleTable from "../components/ScheduleTable";
import SmartAssetLibrary from "./SmartAssetLibrary";

const PRODUCTS = ["羊肚菌", "荔枝菌", "松茸"];
const PLATFORMS = [
  { key: "douyin", label: "抖音" },
  { key: "xiaohongshu", label: "小红书" },
  { key: "shipinhao", label: "视频号" },
  { key: "kuaishou", label: "快手" },
];

export default function ProjectWorkbench() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [schedule, setSchedule] = useState<ScheduleEntry[]>([]);
  const [product, setProduct] = useState(PRODUCTS[0]);
  const [platforms, setPlatforms] = useState<string[]>(["douyin", "xiaohongshu"]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [tab, setTab] = useState<"jobs" | "schedule" | "assets">("jobs");
  const [projectName, setProjectName] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const proj = await api.getProject(id);
      setJobs((proj as { jobs?: JobSummary[] }).jobs || []);
      setProjectName((proj as { name?: string }).name || id);
      setError("");
    } catch (e) {
      console.error("load project failed", e);
      setError("加载项目数据失败");
    }
    try {
      const sched = await api.getSchedule({ project_id: id });
      setSchedule(sched);
    } catch (e) {
      console.error("load schedule failed", e);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const handleUpload = async (file: File) => {
    if (!id) return;
    setSelectedFile(file.name);
    try {
      await api.uploadAsset(id, file);
      load();
    } catch (e) {
      console.error("upload failed", e);
      setError("上传失败");
    }
    setSelectedFile(null);
  };

  const handleCreateJob = async () => {
    if (!id) return;
    try {
      const job = await api.createJob(id, { product, platforms });
      navigate(`/jobs/${job.job_id}`);
    } catch (e) {
      console.error("create job failed", e);
      setError("创建 Job 失败");
    }
  };

  const handleRetry = async (jobId: string) => {
    await api.retryJob(jobId);
    load();
  };

  const handleDeleteJob = async (jobId: string) => {
    if (!window.confirm(`确认删除 Job ${jobId}？此操作不可撤销。`)) return;
    try {
      await api.deleteJob(jobId);
      load();
    } catch (e) {
      console.error("delete job failed", e);
      setError("删除 Job 失败");
    }
  };

  const togglePlatform = (p: string) => {
    setPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <button className="text-gray-500 hover:text-gray-700 text-sm" onClick={() => navigate("/")}>
          &#8592; 项目列表
        </button>
        <span className="text-gray-300">|</span>
        <h1 className="text-lg font-bold">{projectName || id}</h1>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError("")} className="text-red-400 hover:text-red-600 text-lg leading-none">&times;</button>
        </div>
      )}

      {/* Create Job */}
      <section className="border rounded-xl p-5 mb-6 bg-white">
        <h2 className="text-[15px] font-semibold mb-3.5">创建新 Job</h2>
        <div className="flex gap-4 flex-wrap items-end">
          <label className="grid gap-1.5 text-xs text-[#59636e] min-w-[200px]">
            产品选择
            <select
              className="border rounded-lg px-3 py-2 text-sm"
              value={product}
              onChange={(e) => setProduct(e.target.value)}
            >
              {PRODUCTS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>
          <div className="grid gap-1 text-xs text-gray-500">
            <span className="text-xs text-[#59636e]">目标平台</span>
            <div className="flex gap-3 py-2">
              {PLATFORMS.map((p) => (
                <label key={p.key} className="flex items-center gap-1 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={platforms.includes(p.key)}
                    onChange={() => togglePlatform(p.key)}
                  />
                  {p.label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex-1 min-w-64">
            <FileDropzone onFile={handleUpload} />
            {selectedFile && (
              <div className="text-xs text-green-600 mt-1">&#10003; {selectedFile}</div>
            )}
          </div>
          <button
            className="bg-[#d1242f] text-white border-none px-8 py-3 rounded-lg text-[15px] font-semibold hover:brightness-110 transition-all h-fit"
            onClick={handleCreateJob}
          >
            创建并开始生产
          </button>
        </div>
      </section>

      {/* Tab: Jobs / Schedule */}
      <div className="flex gap-4 border-b mb-4">
        <button
          className={`pb-2 text-sm font-medium transition-colors ${
            tab === "jobs"
              ? "border-b-2 border-[#0969da] text-[#0969da]"
              : "text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("jobs")}
        >
          Job 列表
        </button>
        <button
          className={`pb-2 text-sm font-medium transition-colors ${
            tab === "schedule"
              ? "border-b-2 border-[#0969da] text-[#0969da]"
              : "text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("schedule")}
        >
          排期池
        </button>
        <button
          className={`pb-2 text-sm font-medium transition-colors ${
            tab === "assets"
              ? "border-b-2 border-[#0969da] text-[#0969da]"
              : "text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("assets")}
        >
          智能素材库
        </button>
      </div>

      {tab === "jobs" ? (
        <JobTable jobs={jobs} onRetry={handleRetry} onDelete={handleDeleteJob} />
      ) : tab === "schedule" ? (
        <ScheduleTable
          entries={schedule}
          onExport={() => api.exportSchedule()}
        />
      ) : (
        <SmartAssetLibrary projectId={id!} onUpload={handleUpload} />
      )}
    </div>
  );
}
