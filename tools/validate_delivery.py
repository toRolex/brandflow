from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main_controller as mc


SRT_BLOCK_RE = re.compile(r"(?ms)^\s*(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n(.+?)(?=\n\s*\n|\Z)")
ORPHAN_QUESTION_RE = re.compile(r"(?<![\u4e00-\u9fffA-Za-z0-9])[?？]+(?![\u4e00-\u9fffA-Za-z0-9])")
TRADITIONAL_MARKERS = set("這個視頻資後臺裡為與嗎無還會說時對")
TRADITIONAL_TERMS = ("資源堂", "資元堂", "視頻", "這個")


def resolve_tool(root: Path, env_key: str, relative: str) -> Path:
    configured = os.getenv(env_key, "").strip()
    if configured:
        return Path(configured)
    return root / relative


def ffprobe_duration(ffprobe: Path, video: Path) -> float:
    result = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        return float((result.stdout or "").strip())
    except ValueError:
        return 0.0


def validate_srt(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "path": str(path), "errors": ["missing_srt"], "block_count": 0}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    errors: list[str] = []
    blocks = list(SRT_BLOCK_RE.finditer(text.strip()))
    if not blocks:
        errors.append("no_parseable_srt_blocks")
    if "\ufffd" in text or "�" in text:
        errors.append("replacement_character")
    if mc.EMOJI_RE.search(text):
        errors.append("emoji")
    if ORPHAN_QUESTION_RE.search(text):
        errors.append("orphan_question")
    visible_text = "".join(match.group(4) for match in blocks)
    if any(term in visible_text for term in TRADITIONAL_TERMS) or any(char in visible_text for char in TRADITIONAL_MARKERS):
        errors.append("possible_traditional_chinese")
    for match in blocks:
        if not match.group(4).strip():
            errors.append(f"empty_text_block_{match.group(1)}")
            break
    return {"ok": not errors, "path": str(path), "errors": errors, "block_count": len(blocks)}


def load_project(root: Path, project_name: str | None) -> Path:
    if project_name:
        project = root / project_name
        if not project.exists():
            raise FileNotFoundError(project)
        return project
    candidates = [path for path in root.iterdir() if path.is_dir() and mc.parse_project_folder_name(path.name) and (path / "task_status.json").exists()]
    if not candidates:
        raise FileNotFoundError("No 001xxx project with task_status.json was found.")
    return max(candidates, key=lambda path: (path / "task_status.json").stat().st_mtime)


def schedule_rows_ok(root: Path, expected: int) -> dict[str, Any]:
    workbook_path = root / "排期池.xlsx"
    if not workbook_path.exists() or mc.load_workbook is None:
        return {"ok": False, "path": str(workbook_path), "nonempty_rows": 0, "errors": ["missing_or_unreadable_schedule"]}
    workbook = mc.load_workbook(workbook_path)
    sheet = workbook.active
    nonempty_rows = 0
    bad_rows = 0
    for row in sheet.iter_rows(min_row=2, values_only=True):
        values = [str(item or "").strip() for item in row]
        if any(values):
            nonempty_rows += 1
            joined = "\n".join(values)
            if not joined or "成品" not in joined:
                bad_rows += 1
    errors = []
    if nonempty_rows < expected:
        errors.append(f"schedule_rows_lt_{expected}")
    if bad_rows:
        errors.append(f"schedule_bad_rows_{bad_rows}")
    return {"ok": not errors, "path": str(workbook_path), "nonempty_rows": nonempty_rows, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deliverable videos, subtitles, and schedule rows.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--project", default="", help="Project name; defaults to latest project with task_status.json")
    parser.add_argument("--expected", type=int, default=10, help="Expected completed video count")
    parser.add_argument("--min-seconds", type=float, default=35.0)
    parser.add_argument("--max-seconds", type=float, default=45.0)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    project = load_project(root, args.project.strip() or None)
    ffprobe = resolve_tool(root, "FFPROBE_PATH", "tools/bin/ffprobe.exe")
    if not ffprobe.exists():
        raise FileNotFoundError(f"Missing ffprobe: {ffprobe}")

    state = mc.read_json(project / "task_status.json", {})
    completed_jobs = [job for job in state.get("jobs", []) if job.get("state") == mc.TaskState.BURN_COMPLETED.value and not job.get("skipped")]
    video_results = []
    for job in completed_jobs:
        bundle = job.get("asset_bundle", {})
        video_path = Path(bundle.get("final_video_path") or project / "成品" / f"{job['job_id']}_成品.mp4")
        srt_path = Path(bundle.get("srt_path") or project / "工作区" / job["job_id"] / f"{job['job_id']}_字幕.srt")
        duration = ffprobe_duration(ffprobe, video_path) if video_path.exists() else 0.0
        duration_ok = args.min_seconds <= duration <= args.max_seconds
        srt_result = validate_srt(srt_path)
        video_results.append(
            {
                "job_id": job.get("job_id"),
                "video_path": str(video_path),
                "video_exists": video_path.exists(),
                "duration": round(duration, 3),
                "duration_ok": duration_ok,
                "srt": srt_result,
                "title_ok": bool(bundle.get("post_title") or bundle.get("cover_title")),
                "desc_ok": bool(bundle.get("post_desc")),
                "tags_ok": bool(bundle.get("tags")),
            }
        )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": str(project),
        "expected": args.expected,
        "completed_count": len(completed_jobs),
        "completed_count_ok": len(completed_jobs) >= args.expected,
        "duration_range": [args.min_seconds, args.max_seconds],
        "videos": video_results,
        "schedule": schedule_rows_ok(root, args.expected),
    }
    report["ok"] = (
        report["completed_count_ok"]
        and all(item["video_exists"] and item["duration_ok"] and item["srt"]["ok"] and item["title_ok"] and item["desc_ok"] and item["tags_ok"] for item in video_results[: args.expected])
        and report["schedule"]["ok"]
    )

    reports_dir = root / "reports"
    reports_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = reports_dir / f"delivery_acceptance_{stamp}.json"
    md_path = reports_dir / f"delivery_acceptance_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Delivery Acceptance {stamp}",
        "",
        f"- Project: `{project.name}`",
        f"- Expected: {args.expected}",
        f"- Completed: {len(completed_jobs)}",
        f"- Overall: {'PASS' if report['ok'] else 'FAIL'}",
        "",
        "| job | duration | video | srt | title/desc/tags |",
        "|---|---:|---|---|---|",
    ]
    for item in video_results:
        metadata_ok = item["title_ok"] and item["desc_ok"] and item["tags_ok"]
        lines.append(
            f"| {item['job_id']} | {item['duration']:.3f} | {'ok' if item['video_exists'] and item['duration_ok'] else 'fail'} | "
            f"{'ok' if item['srt']['ok'] else ','.join(item['srt']['errors'])} | {'ok' if metadata_ok else 'fail'} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json_path)
    print(md_path)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
