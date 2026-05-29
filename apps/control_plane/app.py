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
from packages.pipeline_services.legacy_media_bridge import LegacyMediaBridge
from packages.pipeline_services.legacy_schedule_bridge import LegacyScheduleBridge
from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge
from packages.pipeline_services.media_utils import write_concat_file, get_media_duration
from main_controller import load_environment

REVIEW_PHASES = {"script_review", "final_review"}
AUTO_TICK_INTERVAL = 3  # seconds between auto-advances in dev mode


def _to_url_path(path: Path, workspace_dir: Path) -> str:
    """Convert a workspace-relative Path to a URL-safe forward-slash path."""
    return path.relative_to(workspace_dir).as_posix()


def _phase_to_artifacts(phase: str, job_id: str, project_dir: Path, root_dir: Path, product: str) -> list[dict]:
    """Execute the real pipeline for the target phase and return artifact pointers."""
    print(f"[PHASE] target={phase}, job={job_id}", flush=True)
    load_environment(root_dir)
    workspace_dir = root_dir / "workspace"
    job_dir = project_dir / "runtime" / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict] = []
    script_bridge = LegacyScriptBridge(root_dir)
    media_bridge = LegacyMediaBridge(root_dir)
    schedule_bridge = LegacyScheduleBridge(root_dir / "排期池.xlsx")

    if phase == "script_generating":
        script_result = script_bridge.generate(product=product, output_dir=job_dir, mock=False)
        txt_path = Path(script_result["txt_path"])
        json_path = Path(script_result["json_path"])
        for p in [txt_path, json_path]:
            if p.exists():
                rel = _to_url_path(p, workspace_dir)
                result.append({"kind": "script", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": p.stat().st_size})

    elif phase == "tts_generating":
        # Find the script text from existing artifacts
        existing_script = None
        for a in job_dir.glob("*口播文案.txt"):
            existing_script = a.read_text(encoding="utf-8").strip()
            break
        if not existing_script:
            # Fallback: read from json
            for a in job_dir.glob("*口播文案.json"):
                jdata = json.loads(a.read_text(encoding="utf-8"))
                existing_script = jdata.get("text", "").strip()
                break
        import sys
        print(f"[TTS DEBUG] phase=tts_generating, script_found={existing_script is not None}, len={len(existing_script) if existing_script else 0}", flush=True)
        if existing_script:
            audio_path = job_dir / "audio.mp3"
            try:
                media_bridge.synthesize_tts(existing_script, audio_path)
                print(f"[TTS] Synthesized: {audio_path.exists()}, size={audio_path.stat().st_size if audio_path.exists() else 0}", flush=True)
            except Exception as e:
                print(f"[TTS ERROR] {type(e).__name__}: {e}", flush=True)
                import traceback; traceback.print_exc()
            if audio_path.exists():
                rel = _to_url_path(audio_path, workspace_dir)
                result.append({"kind": "tts_audio", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": audio_path.stat().st_size})
        else:
            print(f"[TTS WARN] No script text found in {job_dir}", flush=True)
            for f2 in job_dir.iterdir():
                print(f"  file: {f2.name}", flush=True)

    elif phase == "subtitle_generating":
        audio_path = job_dir / "audio.mp3"
        srt_path = job_dir / "subtitles.srt"
        if audio_path.exists():
            # Find script text
            script_text = ""
            for a in job_dir.glob("*口播文案.txt"):
                script_text = a.read_text(encoding="utf-8").strip()
                break
            if script_text:
                media_bridge.build_script_timed_srt(audio_path, srt_path, script_text)
        if srt_path.exists():
            rel = _to_url_path(srt_path, workspace_dir)
            result.append({"kind": "subtitle", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": srt_path.stat().st_size})

    elif phase == "asset_retrieving":
        # Run semantic retrieval: script text → keyword match → selected clips
        script_text = ""
        for a in job_dir.glob("*口播文案.txt"):
            script_text = a.read_text(encoding="utf-8").strip()
            break

        if script_text:
            db_path = project_dir / "asset_index.db"

            from packages.pipeline_services.asset_library import AssetRepository, AssetRetriever
            repo = AssetRepository(db_path)
            retriever = AssetRetriever(repo)

            product = os.environ.get("PRODUCT", "见手青")
            selected = retriever.retrieve(script_text, product)

            clip_list_path = job_dir / "selected_clips.json"
            clip_list_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

            result.append({
                "kind": "selected_clips",
                "relative_path": _to_url_path(clip_list_path, workspace_dir),
                "url": f"/workspace/{_to_url_path(clip_list_path, workspace_dir)}",
                "size_bytes": clip_list_path.stat().st_size,
            })

    elif phase == "video_rendering":
        base_path = job_dir / "base.mp4"
        audio_path = job_dir / "audio.mp3"
        clip_list_path = job_dir / "selected_clips.json"

        if audio_path.exists() and clip_list_path.exists():
            selected = json.loads(clip_list_path.read_text(encoding="utf-8"))
            clip_paths = [Path(item["file_path"]) for item in selected if Path(item["file_path"]).exists()]

            if clip_paths:
                concat_list = job_dir / "concat_list.txt"
                write_concat_file(concat_list, clip_paths)
                audio_duration = get_media_duration(audio_path)
                recipe_idx = hash(job_id) % 4
                recipes = [
                    {"name": "小红书", "vf": "eq=brightness=0.02:contrast=1.03:saturation=1.05"},
                    {"name": "抖音", "vf": "unsharp=5:5:0.8:3:3:0.4,eq=contrast=0.98"},
                    {"name": "视频号", "vf": "hflip,eq=brightness=-0.01:saturation=0.95"},
                    {"name": "快手", "vf": "noise=alls=2:allf=t,eq=contrast=1.02"},
                ]
                recipe = recipes[recipe_idx]
                import random as _random
                vf_combined = f"crop=iw*{1.0 - _random.uniform(0.01, 0.03):.3f}:ih*{1.0 - _random.uniform(0.01, 0.03):.3f},scale=iw:ih,{recipe['vf']}"

                import subprocess as _sp
                ffmpeg = os.environ.get("FFMPEG_PATH", "ffmpeg")
                _sp.run(
                    [ffmpeg, "-f", "concat", "-safe", "0", "-i", str(concat_list),
                     "-vf", vf_combined, "-an", "-t", f"{audio_duration:.3f}",
                     "-c:v", "libx264", "-preset", "superfast", "-crf", "23",
                     "-pix_fmt", "yuv420p", "-y", str(base_path)],
                    check=True, capture_output=True, text=True,
                )
        elif audio_path.exists():
            # Fallback: use legacy bridge for base video construction
            media_bridge.build_base_video(
                project_dir,
                {"job_id": job_id, "asset_bundle": {"audio_path": str(audio_path)}, "sequence": 1},
                base_path,
            )

        if base_path.exists():
            rel = _to_url_path(base_path, workspace_dir)
            result.append({"kind": "video_base", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": base_path.stat().st_size})

    elif phase == "final_review":
        final_path = job_dir / "final.mp4"
        base_path = job_dir / "base.mp4"
        audio_path = job_dir / "audio.mp3"
        srt_path = job_dir / "subtitles.srt"
        if base_path.exists() and audio_path.exists() and srt_path.exists():
            media_bridge.burn_final_video(base_path, audio_path, srt_path, final_path, cover_clip_path=None)
        if final_path.exists():
            rel = _to_url_path(final_path, workspace_dir)
            result.append({"kind": "final_video", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": final_path.stat().st_size})
            # Also write to schedule
            schedule_bridge.append(
                project_dir.name,
                {"job_id": job_id, "asset_bundle": {"post_title": "", "post_desc": "", "cover_title": ""}},
                final_path,
            )

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

                        if not job_id:
                            continue
                        if current in ("completed", "failed", "cancelled", "paused"):
                            continue
                        # Skip review gates that are already pending approval (not yet approved)
                        if current in REVIEW_PHASES and data.get("review_status") not in ("approved",):
                            continue

                        # Process the current phase, then advance if artifacts are produced
                        # or if the phase produces no artifacts (auto-advance to next phase)
                        if current == "queued":
                            target = "script_generating"
                        else:
                            target = current

                        # Execute real pipeline for the target phase
                        product = data.get("product", os.environ.get("PRODUCT", "见手青"))
                        artifacts = _phase_to_artifacts(target, job_id, project_dir, root_dir, product)

                        # Merge artifacts (keep existing, add new ones)
                        existing = data.get("artifacts", [])
                        existing_kinds = {a.get("kind") for a in existing}
                        for a in artifacts:
                            if a["kind"] not in existing_kinds:
                                existing.append(a)
                        data["artifacts"] = existing

                        # Advance to next phase after processing current one
                        # Only advance one phase per auto_tick iteration
                        if target in REVIEW_PHASES:
                            data["phase"] = target
                            data["review_status"] = "pending"
                        elif artifacts:
                            # Artifacts produced, advance to next phase
                            try:
                                data["phase"] = next_phase(target)
                            except ValueError:
                                data["phase"] = "completed"
                        else:
                            # No artifacts produced - auto-advance (transitional phase or error)
                            try:
                                data["phase"] = next_phase(target)
                            except ValueError:
                                data["phase"] = "completed"

                        f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        print(f"[AUTO-TICK] {job_id}: {current} -> {data['phase']} (artifacts: {[a['kind'] for a in artifacts]})")

                        review_path = project_dir / "reviews" / "review_events.jsonl"
                        review_path.parent.mkdir(parents=True, exist_ok=True)
                        with review_path.open("a", encoding="utf-8") as h:
                            h.write(json.dumps({
                                "job_id": job_id,
                                "event": "auto_tick",
                                "from_phase": current,
                                "to_phase": data["phase"],
                            }, ensure_ascii=False) + "\n")
                    except Exception as e:
                        print(f"[AUTO-TICK ERROR] {f.name}: {e}")
                        import traceback; traceback.print_exc()
        except Exception as e:
            print(f"[AUTO-TICK LOOP ERROR] {e}")
            import traceback; traceback.print_exc()


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
