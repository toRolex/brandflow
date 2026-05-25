import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { JobDetail } from "../types";
import PipelineSidebar from "../components/PipelineSidebar";
import ScriptPreview from "../components/ScriptPreview";
import MediaPlayer from "../components/MediaPlayer";
import SubtitleEditor from "../components/SubtitleEditor";

export default function JobPipeline() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [activeStepKey, setActiveStepKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const initialLoad = useRef(true);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const j = await api.getJob(id);
      setJob(j);
      if (initialLoad.current) {
        setActiveStepKey(j.phase);
        initialLoad.current = false;
      }
      setError("");
    } catch (e) {
      console.error("getJob failed", e);
      setError("加载 Job 失败");
    }
    setLoading(false);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!id) return;
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [id, load]);

  if (loading) {
    return <div className="text-center py-12 text-gray-400">加载中...</div>;
  }

  if (!job) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-400 text-sm mb-2">Job 未找到</p>
        {error && <p className="text-red-500 text-xs">{error}</p>}
      </div>
    );
  }

  const handleApprove = async (gate: string) => {
    try {
      await api.approveReview(job.job_id, gate);
      load();
    } catch (e) {
      console.error("approve failed", e);
      setError("审核操作失败");
    }
  };

  const handleReject = async (gate: string) => {
    try {
      await api.rejectReview(job.job_id, gate);
      load();
    } catch (e) {
      console.error("reject failed", e);
      setError("审核操作失败");
    }
  };

  const handleRetry = () => {
    api.retryJob(job.job_id);
  };

  const renderDetail = () => {
    switch (activeStepKey) {
      case "asset_upload":
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">上传素材</h3>
            <MediaPlayer src="" kind="video" />
          </div>
        );
      case "script_gen":
      case "script_review":
        return (
          <ScriptPreview
            script="等待生成..."
            checks={null}
            onApprove={() => handleApprove("script")}
            onReject={() => handleReject("script")}
            onRegenerate={handleRetry}
          />
        );
      case "packaging":
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">生成包装</h3>
            <p className="text-gray-400 text-sm">包装内容（标题、简介、标签）将在脚本审核通过后自动生成</p>
          </div>
        );
      case "tts":
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">TTS 配音</h3>
            <MediaPlayer src="" kind="audio" />
          </div>
        );
      case "subtitle":
        return (
          <SubtitleEditor text="" onSave={(text) => console.log("save subtitle", text)} />
        );
      case "video_base":
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">底包拼接</h3>
            <MediaPlayer src="" kind="video" />
          </div>
        );
      case "asset_review":
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">素材审核</h3>
            <p className="text-gray-400 text-sm mb-4">请确认选用的素材片段是否合适</p>
            <div className="flex gap-2">
              <button
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm"
                onClick={() => handleApprove("asset")}
              >
                {"\u2713"} 通过
              </button>
              <button
                className="bg-red-600 text-white px-4 py-2 rounded-lg text-sm"
                onClick={() => handleReject("asset")}
              >
                {"\u2717"} 打回
              </button>
            </div>
          </div>
        );
      case "final_review":
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">最终视频</h3>
            <MediaPlayer src="" kind="video" />
            <div className="flex gap-2 mt-4">
              <button
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm"
                onClick={() => handleApprove("final")}
              >
                {"\u2713"} 通过
              </button>
              <button
                className="bg-red-600 text-white px-4 py-2 rounded-lg text-sm"
                onClick={() => handleReject("final")}
              >
                {"\u2717"} 打回
              </button>
            </div>
          </div>
        );
      case "schedule":
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">排期发布</h3>
            <p className="text-gray-400 text-sm mb-4">各平台发布信息将在视频审核通过后生成</p>
            <button className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">
              确认发布
            </button>
          </div>
        );
      default:
        return <div className="text-gray-400 text-sm">未知步骤</div>;
    }
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <button
          className="text-gray-500 hover:text-gray-700 text-sm"
          onClick={() => navigate(`/projects/${job.project_id}`)}
        >
          {"\u2190"} 返回工作台
        </button>
        <span className="text-gray-300">|</span>
        <h1 className="text-lg font-bold font-mono">{job.job_id}</h1>
        {job.product && (
          <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
            {job.product}
          </span>
        )}
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError("")} className="text-red-400 hover:text-red-600 text-lg leading-none">&times;</button>
        </div>
      )}

      <div className="flex border rounded-xl overflow-hidden min-h-[500px]">
        <PipelineSidebar
          currentPhase={job.phase}
          completedPhases={[]}
          onStepClick={(key) => setActiveStepKey(key)}
          activeStepKey={activeStepKey}
          jobInfo={job.product ? `${job.job_id} ${job.product}` : job.job_id}
        />
        <div className="flex-1 p-5 bg-[#eff2f5]">{renderDetail()}</div>
      </div>
  );
}
