import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.control_plane.routes.api_jobs import router as api_jobs_router
from apps.control_plane.routes.api_projects import router as api_projects_router
from apps.control_plane.routes.api_schedule import router as api_schedule_router
from apps.control_plane.routes.config import router as config_router
from apps.control_plane.routes.jobs import router as jobs_router
from apps.control_plane.routes.projects import router as projects_router
from apps.control_plane.routes.reviews import router as reviews_router
from apps.control_plane.routes.workers import router as workers_router
from apps.control_plane.services.dispatch import Dispatcher
from packages.domain_core.state import next_phase

REVIEW_PHASES = {"script_review", "asset_review", "final_review"}
AUTO_TICK_INTERVAL = 3  # seconds between auto-advances in dev mode

# Stub artifact content per phase
STUB_SCRIPT = "羊肚菌，大自然的黑色珍宝。滋元堂精选优质羊肚菌，每一朵都源自深山纯净环境，富含多种氨基酸和微量元素。烹饪时请务必充分烹熟，保留鲜美口感的同时确保食用安全。煲汤、清炒皆宜，轻松为家人补充满满营养。选择滋元堂羊肚菌，让健康从舌尖开始。"
STUB_TITLE = "深山羊肚菌 滋补全家 | 滋元堂"
STUB_DESC = "滋元堂精选优质羊肚菌，源自深山纯净环境，充分烹熟更安心。"


def _phase_to_artifacts(phase: str, job_id: str, project_dir: Path, root_dir: Path) -> list[dict]:
    """Generate stub artifact files for the target phase and return artifact pointers."""
    workspace_dir = root_dir / "workspace"
    artifacts_dir = project_dir / "runtime" / "jobs" / job_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict] = []

    if phase == "script_generating":
        script_path = artifacts_dir / "script.txt"
        script_path.write_text(STUB_SCRIPT, encoding="utf-8")
        rel = str(script_path.relative_to(workspace_dir))
        result.append({"kind": "script", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": len(STUB_SCRIPT.encode())})

    elif phase == "tts_generating":
        audio_path = artifacts_dir / "tts.mp3"
        audio_path.write_bytes(b"stub-audio")
        rel = str(audio_path.relative_to(workspace_dir))
        result.append({"kind": "tts_audio", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": 10})

    elif phase == "subtitle_generating":
        srt_path = artifacts_dir / "subtitle.srt"
        srt_path.write_text("1\n00:00:00,000 --> 00:00:05,000\n羊肚菌，大自然的黑色珍宝。\n", encoding="utf-8")
        rel = str(srt_path.relative_to(workspace_dir))
        result.append({"kind": "subtitle", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": 60})

    elif phase == "asset_retrieving":
        pass  # assets already uploaded by user

    elif phase == "video_rendering":
        video_path = artifacts_dir / "base.mp4"
        video_path.write_bytes(b"stub-base-video")
        rel = str(video_path.relative_to(workspace_dir))
        result.append({"kind": "video_base", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": 15})

    elif phase == "final_review":
        final_path = artifacts_dir / "final.mp4"
        final_path.write_bytes(b"stub-final-video")
        rel = str(final_path.relative_to(workspace_dir))
        result.append({"kind": "final_video", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": 20})

    elif phase == "schedule_writing":
        pass

    return result


async def _auto_tick(root_dir: Path):
    """Dev-mode background loop: scans disk for non-review jobs, generates stub artifacts, and advances them."""
    while True:
        await asyncio.sleep(AUTO_TICK_INTERVAL)
        try:
            projects_root = root_dir / "workspace" / "projects"
            if not projects_root.exists():
                continue

            for project_dir in sorted(projects_root.iterdir()):
                if not project_dir.is_dir():
                    continue
                jobs_dir = project_dir / "control" / "jobs"
                if not jobs_dir.exists():
                    continue

                for f in sorted(jobs_dir.glob("*.json")):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        job_id = data.get("job_id", "")
                        current = data.get("phase", "")

                        if not job_id or current in REVIEW_PHASES:
                            continue
                        if current in ("completed", "failed", "cancelled", "paused"):
                            continue

                        if current == "queued":
                            next_p = "script_generating"
                        else:
                            try:
                                next_p = next_phase(current)
                            except ValueError:
                                next_p = "completed"

                        # Generate stub artifacts for the target phase
                        stubs = _phase_to_artifacts(next_p, job_id, project_dir, root_dir)

                        # Merge artifacts (keep existing, add new stubs)
                        existing = data.get("artifacts", [])
                        existing_kinds = {a.get("kind") for a in existing}
                        for s in stubs:
                            if s["kind"] not in existing_kinds:
                                existing.append(s)

                        data["artifacts"] = existing

                        if next_p in REVIEW_PHASES:
                            data["phase"] = next_p
                            data["review_status"] = "pending"
                        else:
                            data["phase"] = next_p

                        f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        print(f"[AUTO-TICK] {job_id}: {current} -> {next_p} (artifacts: {[a['kind'] for a in stubs]})")

                        review_path = project_dir / "reviews" / "review_events.jsonl"
                        review_path.parent.mkdir(parents=True, exist_ok=True)
                        with review_path.open("a", encoding="utf-8") as h:
                            h.write(json.dumps({
                                "job_id": job_id,
                                "event": "auto_tick",
                                "from_phase": current,
                                "to_phase": next_p,
                            }, ensure_ascii=False) + "\n")
                    except Exception as e:
                        print(f"[AUTO-TICK ERROR] {f.name}: {e}")
        except Exception as e:
            print(f"[AUTO-TICK LOOP ERROR] {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    dev_mode = os.environ.get("DEV_AUTO_TICK", "1") == "1"
    if dev_mode:
        asyncio.create_task(_auto_tick(app.state.root_dir))
    yield


def create_app(root_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Ziyuantang Control Plane", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.dispatcher = Dispatcher()
    app.state.root_dir = root_dir or Path.cwd()
    app.include_router(api_projects_router)
    app.include_router(api_jobs_router)
    app.include_router(api_schedule_router)
    app.include_router(projects_router)
    app.include_router(config_router)
    app.include_router(workers_router)
    app.include_router(jobs_router)
    app.include_router(reviews_router)

    workspace = root_dir or Path.cwd() / "workspace"
    if workspace.exists():
        app.mount("/workspace", StaticFiles(directory=str(workspace)), name="workspace")

    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app
