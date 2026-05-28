import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { JobDetail, Phase } from "../types";
import { PIPELINE_STEPS } from "../types";
import PipelineSidebar from "../components/PipelineSidebar";
import ScriptPreview from "../components/ScriptPreview";
import MediaPlayer from "../components/MediaPlayer";
import SubtitleEditor from "../components/SubtitleEditor";

function computeCompletedPhases(currentPhase: Phase): Phase[] {
  const terminalPhases: Phase[] = ["completed", "failed", "cancelled", "paused"];
  const nonTerminalSteps = PIPELINE_STEPS.filter((s) => !terminalPhases.includes(s.phase));
  if (terminalPhases.includes(currentPhase)) {
    if (currentPhase === "completed") {
      return [...nonTerminalSteps.map((s) => s.phase), "completed"];
    }
    return [currentPhase];
  }
  const order = PIPELINE_STEPS.map((s) => s.phase);
  const idx = order.indexOf(currentPhase);
  if (idx <= 0) return [];
  return order.slice(0, idx).filter((p, i, arr) => arr.indexOf(p) === i) as Phase[];
}

export default function JobPipeline() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [activeStepKey, setActiveStepKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [scriptContent, setScriptContent] = useState("");
  const initialLoad = useRef(true);

  const phaseToStepKey = (phase: Phase): string => {
    const step = PIPELINE_STEPS.find((s) => s.phase === phase);
    return step ? step.key : "";
  };

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const j = await api.getJob(id);
      setJob(j);
      if (initialLoad.current) {
        setActiveStepKey(phaseToStepKey(j.phase));
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

  // Sync activeStepKey when backend phase changes (auto_tick advances)
  const prevPhaseRef = useRef(job?.phase);
  useEffect(() => {
    if (!job) return;
    if (job.phase !== prevPhaseRef.current) {
      prevPhaseRef.current = job.phase;
      setActiveStepKey(phaseToStepKey(job.phase));
    }
  }, [job?.phase]);

  // Fetch script content when script artifact changes
  useEffect(() => {
    if (!job) return;
    const scriptArtifact = job.artifacts?.find((a) => a.kind === "script");
    if (scriptArtifact?.url) {
      fetch(scriptArtifact.url).then(r => r.text()).then(setScriptContent).catch(() => setScriptContent(""));
    } else {
      setScriptContent("");
    }
  }, [job, job?.artifacts]);

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

  const findArtifact = (kind: string) => {
    return job.artifacts?.find((a) => a.kind === kind);
  };

  const renderDetail = () => {
    switch (activeStepKey) {
      case "queued":
        return <div className="text-gray-400 text-sm py-4">任务排队中，等待系统调度...</div>;
      case "script_gen":
      case "script_review": {
        const scriptArtifact = findArtifact("script");
        return (
          <ScriptPreview
            script={scriptContent || (scriptArtifact ? "加载中..." : "等待生成...")}
            checks={null}
            onApprove={() => handleApprove("script")}
            onReject={() => handleReject("script")}
            onRegenerate={handleRetry}
          />
        );
      }
      case "tts": {
        const audio = findArtifact("tts_audio");
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">TTS 配音</h3>
            <MediaPlayer src={audio?.url || ""} kind="audio" />
          </div>
        );
      }
      case "subtitle":
        return (
          <SubtitleEditor text="" onSave={(text) => console.log("save subtitle", text)} />
        );
      case "video_base": {
        const video = findArtifact("video_base");
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">底包拼接</h3>
            <MediaPlayer src={video?.url || ""} kind="video" />
          </div>
        );
      }
            case "final_review": {
        const finalVideo = findArtifact("final_video");
        return (
          <div>
            <h3 className="font-semibold text-sm mb-3">终审 · 烧录</h3>
            <MediaPlayer src={finalVideo?.url || ""} kind="video" />
            <div className="flex gap-2 mt-4">
              <button
                className="bg-[#0969da] text-white border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
                onClick={() => handleApprove("final")}
              >
                {"\u2713"} 通过
              </button>
              <button
                className="bg-[#d1242f] text-white border-none px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
                onClick={() => handleReject("final")}
              >
                {"\u2717"} 打回
              </button>
            </div>
          </div>
        );
      }
      case "completed": {
        const finalVideo = findArtifact("final_video");
        return (
          <div className="text-center py-12">
            <div className="text-[#1a7f37] text-5xl mb-4">{"✓"}</div>
            <h3 className="text-lg font-semibold text-[#1a7f37] mb-2">生产完成</h3>
            <p className="text-gray-400 text-sm mb-4">视频已生成并排期发布</p>
            <MediaPlayer src={finalVideo?.url || ""} kind="video" />
          </div>
        );
      }
      case "failed":
        return (
          <div className="text-center py-12">
            <div className="text-[#cf222e] text-5xl mb-4">{"✗"}</div>
            <h3 className="text-lg font-semibold text-[#cf222e] mb-2">任务失败</h3>
            <p className="text-gray-400 text-sm">{job.last_error || "未知错误"}</p>
            <button
              className="mt-4 bg-[#0969da] text-white px-4 py-2 rounded-md text-xs hover:brightness-110 transition-all"
              onClick={handleRetry}
            >
              {"↻"} 重试
            </button>
          </div>
        );
      case "cancelled":
        return (
          <div className="text-center py-12">
            <div className="text-gray-400 text-5xl mb-4">{"⊘"}</div>
            <h3 className="text-lg font-semibold text-gray-400 mb-2">已取消</h3>
            <p className="text-gray-400 text-sm">该任务已被人工取消</p>
          </div>
        );
      case "paused":
        return (
          <div className="text-center py-12">
            <div className="text-[#9a6700] text-5xl mb-4">{"⏸"}</div>
            <h3 className="text-lg font-semibold text-[#9a6700] mb-2">已暂停</h3>
            <p className="text-gray-400 text-sm">任务已暂停，可点击"重试当前"继续</p>
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
          completedPhases={computeCompletedPhases(job.phase)}
          onStepClick={(key) => setActiveStepKey(key)}
          activeStepKey={activeStepKey}
          jobInfo={job.product ? `${job.job_id} ${job.product}` : job.job_id}
          onPause={() => api.pauseJob(job.job_id)}
          onRetry={handleRetry}
          onViewLogs={async () => {
            try {
              const r = await api.getJobLogs(job.job_id);
              alert(r.logs || "无日志");
            } catch {
              alert("无法加载日志");
            }
          }}
        />
        <div className="flex-1 p-5 bg-[#eff2f5]">{renderDetail()}</div>
      </div>
    </div>
  );
}
