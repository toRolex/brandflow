import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { JobSummary, AssetFile, ScheduleEntry } from "../types";
import FileDropzone from "../components/FileDropzone";
import JobTable from "../components/JobTable";
import AssetCard from "../components/AssetCard";
import ScheduleTable from "../components/ScheduleTable";

const PRODUCTS = ["羊肚菌", "见手青", "松茸"];
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
  const [assets, setAssets] = useState<AssetFile[]>([]);
  const [schedule, setSchedule] = useState<ScheduleEntry[]>([]);
  const [product, setProduct] = useState(PRODUCTS[0]);
  const [platforms, setPlatforms] = useState<string[]>(["douyin", "xiaohongshu"]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [tab, setTab] = useState<"jobs" | "schedule">("jobs");
  const [projectName, setProjectName] = useState("");

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [proj, assetList] = await Promise.all([
        api.getProject(id),
        api.listAssets(id),
      ]);
      setJobs((proj as { jobs?: JobSummary[] }).jobs || []);
      setAssets(assetList);
      setProjectName((proj as { name?: string }).name || id);
    } catch { /* silently fail */ }
    try {
      const sched = await api.getSchedule({ project_id: id });
      setSchedule(sched);
    } catch { /* silently fail */ }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const handleUpload = async (file: File) => {
    if (!id) return;
    setSelectedFile(file.name);
    try {
      await api.uploadAsset(id, file);
      load();
    } catch { /* silently fail */ }
    setSelectedFile(null);
  };

  const handleCreateJob = async () => {
    if (!id) return;
    try {
      const job = await api.createJob(id, { product, platforms });
      navigate(`/jobs/${job.job_id}`);
    } catch { /* silently fail */ }
  };

  const handleRetry = async (jobId: string) => {
    await api.retryJob(jobId);
    load();
  };

  const handleDeleteAsset = async (name: string) => {
    if (!id) return;
    await api.deleteAsset(id, name);
    load();
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

      {/* Create Job */}
      <section className="border rounded-xl p-5 mb-6 bg-white">
        <h2 className="font-semibold mb-4">创建新 Job</h2>
        <div className="flex gap-4 flex-wrap items-end">
          <label className="grid gap-1 text-xs text-gray-500">
            产品
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
            <span>目标平台</span>
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
            className="bg-red-600 text-white px-6 py-2.5 rounded-lg text-sm font-semibold hover:bg-red-700 transition-colors h-fit"
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
              ? "border-b-2 border-blue-600 text-blue-600"
              : "text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("jobs")}
        >
          Job 列表
        </button>
        <button
          className={`pb-2 text-sm font-medium transition-colors ${
            tab === "schedule"
              ? "border-b-2 border-blue-600 text-blue-600"
              : "text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setTab("schedule")}
        >
          排期池
        </button>
      </div>

      {tab === "jobs" ? (
        <>
          <JobTable jobs={jobs} onRetry={handleRetry} />
          <section className="mt-6">
            <h2 className="font-semibold mb-3">素材库</h2>
            <div className="flex gap-3 overflow-x-auto pb-2">
              {assets.map((a) => (
                <AssetCard key={a.name} asset={a} onDelete={handleDeleteAsset} />
              ))}
              <div
                className="w-44 h-36 border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center cursor-pointer flex-shrink-0 hover:border-gray-400 transition-colors"
                onClick={() => {
                  const inp = document.createElement("input");
                  inp.type = "file";
                  inp.accept = "video/*";
                  inp.onchange = () => {
                    const f = inp.files?.[0];
                    if (f) handleUpload(f);
                  };
                  inp.click();
                }}
              >
                <span className="text-gray-400 text-2xl">&#xFF0B;</span>
              </div>
            </div>
          </section>
        </>
      ) : (
        <ScheduleTable
          entries={schedule}
          onExport={() => api.exportSchedule()}
        />
      )}
    </div>
  );
}
