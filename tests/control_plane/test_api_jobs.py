from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _make_client(tmp_path: Path):
    return TestClient(create_app(tmp_path))


def _configure_scene_folders(
    tmp_path: Path,
    folders: list[tuple[str, str]],
    *,
    with_videos: bool = True,
) -> None:
    """Write scene config and create folders with optional video files."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, str]] = []
    for name, rel_path in folders:
        entries.append({"name": name, "path": rel_path})
        folder_path = tmp_path / "workspace" / rel_path
        folder_path.mkdir(parents=True, exist_ok=True)
        if with_videos:
            (folder_path / "clip.mp4").write_bytes(b"fake video content")
    config = {
        "scene": {
            "folders": entries,
            "transition_duration_ms": 500,
        },
    }
    (config_dir / "app_config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )


# ── 手动脚本更新不影响模式路由 ────────────────────────────────────


def test_update_manual_script_preserves_import_mode(tmp_path: Path) -> None:
    """修改 manual_script 后，import 模式任务仍保持 import 模式。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "初始文案",
            "scene_folder_ids": ["scenes/one"],
        },
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    resp = client.post(
        f"/api/jobs/{job_id}/script",
        json={"manual_script": "修改后的文案"},
    )
    assert resp.status_code == 200

    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["mode"] == "import"
    assert detail["manual_script"] == "修改后的文案"


# ── 单个 create_job ──────────────────────────────────────────────


def test_create_job_persists_manual_script_in_generate_mode(tmp_path: Path) -> None:
    """单次 create_job 在 generate 模式下保留 manual_script 字段。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "generate",
            "manual_script": "这是用户手动输入的口播文案",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "generate"
    assert data["manual_script"] == "这是用户手动输入的口播文案"

    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{data['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    assert raw["manual_script"] == "这是用户手动输入的口播文案"
    assert raw["mode"] == "generate"


def test_create_job_persists_skip_subtitle(tmp_path: Path) -> None:
    """单次 create_job 将 skip_subtitle=True 写入 JobRecord。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "skip_subtitle": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skip_subtitle"] is True

    # 从磁盘直接读 JobRecord 验证持久化
    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{data['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    assert raw["skip_subtitle"] is True


def test_create_job_exposes_pending_execution_state(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    response = client.post(
        "/api/projects/prj_001/jobs",
        json={"product": "test", "platforms": ["douyin"]},
    )

    assert response.status_code == 200
    assert response.json()["execution"] == {
        "status": "pending",
        "current_attempt": 0,
        "max_attempts": 3,
        "error": None,
    }


def test_get_job_round_trips_failed_execution_state(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={"product": "test", "platforms": ["douyin"]},
    ).json()
    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{created['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    raw["execution"] = {
        "status": "failed",
        "current_attempt": 3,
        "max_attempts": 3,
        "error": {
            "code": "TTS_PROVIDER_UNAVAILABLE",
            "message": "配音服务暂时不可用，请稍后重试。",
            "retryable": True,
        },
    }
    job_path.write_text(json.dumps(raw), encoding="utf-8")

    response = client.get(f"/api/jobs/{created['job_id']}")

    assert response.status_code == 200
    assert response.json()["execution"] == raw["execution"]


def test_failed_job_response_exposes_failed_phase(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={"product": "test", "platforms": ["douyin"]},
    ).json()
    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{created['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    raw.update(
        {
            "phase": "failed",
            "failed_phase": "video_rendering",
            "execution": {
                "status": "failed",
                "current_attempt": 3,
                "max_attempts": 3,
                "error": {
                    "code": "VIDEO_SOURCE_MISSING",
                    "message": "No video source.",
                    "retryable": False,
                },
            },
        }
    )
    job_path.write_text(json.dumps(raw), encoding="utf-8")

    response = client.get(f"/api/jobs/{created['job_id']}")

    assert response.status_code == 200
    assert response.json()["failed_phase"] == "video_rendering"


def test_retry_restores_failed_phase_and_preserves_artifacts(tmp_path: Path) -> None:
    """retry 失败后恢复 failed_phase 并保留 artifacts。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "scene_folder_ids": ["scenes/one"],
        },
    ).json()
    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{created['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    artifact = {
        "kind": "scene_segment",
        "relative_path": "scene.mp4",
        "url": "",
        "sha256": "",
        "size_bytes": 1,
        "active": False,
    }
    raw.update(
        {
            "phase": "failed",
            "failed_phase": "video_rendering",
            "artifacts": [artifact],
            "execution": {
                "status": "failed",
                "current_attempt": 3,
                "max_attempts": 3,
                "error": {
                    "code": "MEDIA_PROCESSING_TIMEOUT",
                    "message": "Timed out.",
                    "retryable": True,
                },
            },
        }
    )
    job_path.write_text(json.dumps(raw), encoding="utf-8")
    job_runtime = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "runtime"
        / "jobs"
        / created["job_id"]
    )
    job_runtime.mkdir(parents=True)
    (job_runtime / "montage_segment.mp4").write_bytes(b"fixed input")

    response = client.post(f"/api/jobs/{created['job_id']}/retry")

    assert response.status_code == 200
    saved = json.loads(job_path.read_text(encoding="utf-8"))
    assert saved["phase"] == "video_rendering"
    assert saved["failed_phase"] is None
    assert saved["artifacts"] == [artifact]
    assert saved["execution"]["status"] == "pending"
    assert saved["execution"]["current_attempt"] == 0


def test_retry_revalidates_with_media_handler_contract(tmp_path: Path) -> None:
    """retry 时通过 media handler 的 validate_phase_input 重新校验。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "scene_folder_ids": ["scenes/one"],
        },
    ).json()
    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{created['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    raw.update(
        {
            "phase": "failed",
            "failed_phase": "video_rendering",
            "execution": {
                "status": "failed",
                "current_attempt": 1,
                "max_attempts": 3,
                "error": {
                    "code": "VIDEO_SOURCE_MISSING",
                    "message": "No source.",
                    "retryable": False,
                },
            },
        }
    )
    job_path.write_text(json.dumps(raw), encoding="utf-8")

    response = client.post(f"/api/jobs/{created['job_id']}/retry")

    # Retry revalidates via the media handler contract: video_rendering now
    # requires montage_segment.mp4 (#264), so the fresh validation error
    # replaces the stale stored code.
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "VIDEO_MONTAGE_SEGMENT_MISSING"
    saved = json.loads(job_path.read_text(encoding="utf-8"))
    assert saved["phase"] == "failed"
    assert saved["failed_phase"] == "video_rendering"


def test_retry_legacy_failed_job_without_failed_phase_resets_to_queued(
    tmp_path: Path,
) -> None:
    """存量失败 job（failed_phase 为空）保留旧的重置为 queued 重试行为。"""
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={"product": "test", "platforms": ["douyin"]},
    ).json()
    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{created['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    raw.update({"phase": "failed", "review_status": "none"})
    raw.pop("failed_phase", None)
    job_path.write_text(json.dumps(raw), encoding="utf-8")

    response = client.post(f"/api/jobs/{created['job_id']}/retry")

    assert response.status_code == 200
    assert response.json()["status"] == "queued_for_retry"
    saved = json.loads(job_path.read_text(encoding="utf-8"))
    assert saved["phase"] == "queued"
    assert saved["execution"]["status"] == "pending"


def test_retry_non_failed_job_is_rejected(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={"product": "test", "platforms": ["douyin"]},
    ).json()

    response = client.post(f"/api/jobs/{created['job_id']}/retry")

    assert response.status_code == 409


def test_create_job_persists_language_and_cover_title(tmp_path: Path) -> None:
    """单次 create_job 将 language 与 cover_title 写入 JobRecord。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "language": "cantonese",
            "cover_title": {
                "text": "鲜嫩荔枝菌",
                "highlight_words": ["荔枝菌"],
                "style": {
                    "primary_color": "#FFFF00",
                    "outline_color": "#000000",
                    "highlight_color": "#FF0000",
                    "outline_width": 3,
                    "position": "top",
                },
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["language"] == "cantonese"
    assert data["cover_title"]["text"] == "鲜嫩荔枝菌"
    assert data["cover_title"]["highlight_words"] == ["荔枝菌"]
    assert data["cover_title"]["style"]["position"] == "top"

    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{data['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    assert raw["language"] == "cantonese"
    assert raw["cover_title"]["text"] == "鲜嫩荔枝菌"
    assert raw["cover_title"]["style"]["outline_width"] == 3


def test_batch_create_jobs_persists_manual_script_in_generate_mode(
    tmp_path: Path,
) -> None:
    """批量创建多个 generate 模式任务时，每个 JobRecord 都保留对应 manual_script。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "荔枝菌",
            "platforms": ["douyin"],
            "jobs": [
                {
                    "name": "智能文案一",
                    "mode": "generate",
                    "manual_script": "这是第一条手动文案",
                },
                {
                    "name": "智能文案二",
                    "mode": "generate",
                    "manual_script": "这是第二条手动文案",
                },
            ],
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    assert results[0]["manual_script"] == "这是第一条手动文案"
    assert results[1]["manual_script"] == "这是第二条手动文案"
    assert results[0]["mode"] == "generate"
    assert results[1]["mode"] == "generate"

    for r, expected in zip(results, ["这是第一条手动文案", "这是第二条手动文案"]):
        job_path = (
            tmp_path
            / "workspace"
            / "projects"
            / "prj_001"
            / "control"
            / "jobs"
            / f"{r['job_id']}.json"
        )
        raw = json.loads(job_path.read_text(encoding="utf-8"))
        assert raw["manual_script"] == expected
        assert raw["mode"] == "generate"


def test_batch_create_jobs_persists_cover_title_and_language(tmp_path: Path) -> None:
    """批量创建时 per-job cover_title 与 language 落盘。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "荔枝菌",
            "platforms": ["douyin"],
            "jobs": [
                {
                    "name": "粤语封面",
                    "language": "cantonese",
                    "cover_title": {"text": "鮮嫩荔枝菌", "highlight_words": ["鮮嫩"]},
                },
                {
                    "name": "普通话封面",
                    "cover_title": {
                        "text": "鲜嫩荔枝菌",
                        "highlight_words": ["荔枝菌"],
                    },
                },
            ],
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    assert results[0]["language"] == "cantonese"
    assert results[0]["cover_title"]["text"] == "鮮嫩荔枝菌"
    assert results[1]["language"] == "mandarin"
    assert results[1]["cover_title"]["text"] == "鲜嫩荔枝菌"

    for r in results:
        job_path = (
            tmp_path
            / "workspace"
            / "projects"
            / "prj_001"
            / "control"
            / "jobs"
            / f"{r['job_id']}.json"
        )
        raw = json.loads(job_path.read_text(encoding="utf-8"))
        assert raw["cover_title"]["text"] == r["cover_title"]["text"]
        assert raw["language"] == r["language"]


def test_create_job_persists_auto_approve(tmp_path: Path) -> None:
    """单次 create_job 将 auto_approve=True 写入 JobRecord。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "auto_approve": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["auto_approve"] is True

    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{data['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    assert raw["auto_approve"] is True


def test_create_job_defaults_skip_subtitle_false(tmp_path: Path) -> None:
    """未传 skip_subtitle 时默认值为 False。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["skip_subtitle"] is False


# ── 批量创建接口 ─────────────────────────────────────────────────


def test_batch_create_jobs_basic(tmp_path: Path) -> None:
    """批量创建 2 个 job，返回正确的 display_index。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "荔枝菌",
            "platforms": ["douyin", "xiaohongshu"],
            "jobs": [
                {"name": "第一条", "manual_script": "这是第一条文案"},
                {"name": "第二条", "manual_script": "这是第二条文案"},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["product"] == "荔枝菌"
    assert len(data["results"]) == 2

    r1 = data["results"][0]
    r2 = data["results"][1]
    assert r1["display_index"] == "001"
    assert r1["name"] == "第一条"
    assert r1["product"] == "荔枝菌"
    assert r1["phase"] == "queued"
    assert r2["display_index"] == "002"
    assert r2["name"] == "第二条"

    # 每个 job 都能通过 GET /api/jobs/{job_id} 查回
    for r in data["results"]:
        detail = client.get(f"/api/jobs/{r['job_id']}")
        assert detail.status_code == 200
        assert detail.json()["product"] == "荔枝菌"


def test_batch_create_jobs_display_index_offset(tmp_path: Path) -> None:
    """批量创建时 display_index 从已有 job 数 + 1 开始。"""
    client = _make_client(tmp_path)
    # 先创建 2 个 job
    client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
        },
    )
    client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
        },
    )

    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "荔枝菌",
            "platforms": ["douyin"],
            "jobs": [
                {"name": "批量1"},
                {"name": "批量2"},
            ],
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["display_index"] == "003"
    assert results[1]["display_index"] == "004"


def test_batch_create_jobs_per_job_skip_subtitle(tmp_path: Path) -> None:
    """批量请求中 per-job 的 skip_subtitle 能持久化到磁盘。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "荔枝菌",
            "platforms": ["douyin"],
            "jobs": [
                {"name": "无字幕", "manual_script": "", "skip_subtitle": True},
                {"name": "有字幕", "manual_script": "", "skip_subtitle": False},
            ],
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["skip_subtitle"] is True
    assert results[1]["skip_subtitle"] is False

    # 磁盘验证
    for r in results:
        job_path = (
            tmp_path
            / "workspace"
            / "projects"
            / "prj_001"
            / "control"
            / "jobs"
            / f"{r['job_id']}.json"
        )
        raw = json.loads(job_path.read_text(encoding="utf-8"))
        if r["name"] == "无字幕":
            assert raw["skip_subtitle"] is True
        else:
            assert raw["skip_subtitle"] is False


def test_batch_create_jobs_top_level_auto_approve(tmp_path: Path) -> None:
    """批量请求顶层 auto_approve=True 对所有 job 生效并落盘。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "荔枝菌",
            "platforms": ["douyin"],
            "auto_approve": True,
            "jobs": [
                {"name": "自动审核1"},
                {"name": "自动审核2"},
            ],
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    for r in results:
        assert r["auto_approve"] is True
        job_path = (
            tmp_path
            / "workspace"
            / "projects"
            / "prj_001"
            / "control"
            / "jobs"
            / f"{r['job_id']}.json"
        )
        raw = json.loads(job_path.read_text(encoding="utf-8"))
        assert raw["auto_approve"] is True


def test_create_job_tts_model_and_voice(tmp_path: Path) -> None:
    """单次 create_job 将 tts_model/tts_voice 写入 JobRecord 并返回。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "tts_model": "mimo-v2.5-tts",
            "tts_voice": "茉莉",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tts_model"] == "mimo-v2.5-tts"
    assert data["tts_voice"] == "茉莉"

    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{data['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    assert raw["tts_model"] == "mimo-v2.5-tts"
    assert raw["tts_voice"] == "茉莉"


def test_create_job_tts_defaults_empty(tmp_path: Path) -> None:
    """未传 tts_model/tts_voice 时默认值为空字符串。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={"product": "test", "platforms": ["douyin"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tts_model"] == ""
    assert data["tts_voice"] == ""


def test_batch_create_jobs_tts_model_and_voice(tmp_path: Path) -> None:
    """批量创建时 per-job 的 tts_model/tts_voice 持久化到磁盘。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "荔枝菌",
            "platforms": ["douyin"],
            "jobs": [
                {"name": "默认音色"},
                {"name": "指定音色", "tts_voice": "冰糖"},
            ],
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["tts_voice"] == ""
    assert results[1]["tts_voice"] == "冰糖"

    for r, expected_voice in zip(results, ["", "冰糖"]):
        job_path = (
            tmp_path
            / "workspace"
            / "projects"
            / "prj_001"
            / "control"
            / "jobs"
            / f"{r['job_id']}.json"
        )
        raw = json.loads(job_path.read_text(encoding="utf-8"))
        assert raw["tts_voice"] == expected_voice


def test_batch_create_jobs_empty_list(tmp_path: Path) -> None:
    """空 jobs 列表返回空 results，不算错误。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "荔枝菌",
            "platforms": ["douyin"],
            "jobs": [],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []


# ── audio_source 字段 ────────────────────────────────────────────


def test_create_job_audio_source_tts(tmp_path: Path) -> None:
    """单次 create_job 默认 audio_source='tts' 写入 JobRecord。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["audio_source"] == "tts"

    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{data['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    assert raw["audio_source"] == "tts"


def test_create_job_audio_source_upload(tmp_path: Path) -> None:
    """单次 create_job 传入 audio_source='upload' 持久化到磁盘。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "audio_source": "upload",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["audio_source"] == "upload"

    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{data['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    assert raw["audio_source"] == "upload"


def test_create_job_audio_source_library(tmp_path: Path) -> None:
    """单次 create_job 传入 audio_source='library' 持久化到磁盘。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "audio_source": "library",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["audio_source"] == "library"

    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{data['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    assert raw["audio_source"] == "library"


def test_batch_create_jobs_audio_source(tmp_path: Path) -> None:
    """批量创建时 per-job 的 audio_source 持久化到磁盘。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "荔枝菌",
            "platforms": ["douyin"],
            "jobs": [
                {"name": "TTS配音", "audio_source": "tts"},
                {"name": "上传音频", "audio_source": "upload"},
                {"name": "音乐库", "audio_source": "library"},
            ],
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["audio_source"] == "tts"
    assert results[1]["audio_source"] == "upload"
    assert results[2]["audio_source"] == "library"

    for r, expected in zip(results, ["tts", "upload", "library"]):
        job_path = (
            tmp_path
            / "workspace"
            / "projects"
            / "prj_001"
            / "control"
            / "jobs"
            / f"{r['job_id']}.json"
        )
        raw = json.loads(job_path.read_text(encoding="utf-8"))
        assert raw["audio_source"] == expected


# ── 音乐库 API ───────────────────────────────────────────────────


def test_get_music_empty_library(tmp_path: Path) -> None:
    """音乐库为空时返回空列表。"""
    # 确保 music_library 目录存在但为空
    music_dir = tmp_path / "workspace" / "music_library"
    music_dir.mkdir(parents=True, exist_ok=True)
    client = _make_client(tmp_path)
    resp = client.get("/api/music")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tracks"] == []


def test_get_music_scans_audio_files(tmp_path: Path) -> None:
    """音乐库扫描返回音频文件元信息。"""
    music_dir = tmp_path / "workspace" / "music_library"
    music_dir.mkdir(parents=True, exist_ok=True)
    # 创建一个占位音频文件（无法获取真实时长，但路径信息应正确）
    (music_dir / "bgm_test.mp3").write_bytes(b"fake mp3 content")
    (music_dir / "intro.wav").write_bytes(b"fake wav content")

    client = _make_client(tmp_path)
    resp = client.get("/api/music")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tracks"]) == 2

    names = {t["filename"] for t in data["tracks"]}
    assert names == {"bgm_test.mp3", "intro.wav"}

    for t in data["tracks"]:
        assert "filename" in t
        assert "relative_path" in t
        assert t["relative_path"].startswith("workspace/music_library/")
        assert t["relative_path"].endswith(t["filename"])


# ── 原有 delete job 测试 ─────────────────────────────────────────


def test_delete_job_success(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    # Create a job first
    client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
        },
    )
    # Find the job_id from the response
    jobs = client.get("/api/projects/prj_001").json().get("jobs", [])
    assert len(jobs) == 1
    job_id = jobs[0]["job_id"]

    resp = client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "job_id": job_id}

    # Verify job is gone
    resp2 = client.get(f"/api/jobs/{job_id}")
    assert resp2.status_code == 404


def test_delete_job_not_found(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.delete("/api/jobs/nonexistent_job")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "job not found"}


# ── import 模式场景文件夹验证 ──────────────────────────────────────


def test_create_import_job_rejects_empty_scene_folders(tmp_path: Path) -> None:
    """import 模式创建 Job 时未选择场景文件夹应被拒绝。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "文案",
            "scene_folder_ids": [],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "SCENE_INPUT_MISSING"


def test_create_import_job_rejects_missing_scene_folder(tmp_path: Path) -> None:
    """import 模式选择不存在的场景文件夹路径应返回具体名称。"""
    _configure_scene_folders(
        tmp_path, [("场景一", "scenes/one"), ("场景二", "scenes/two")]
    )
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "文案",
            "scene_folder_ids": ["scenes/one", "scenes/missing"],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "scenes/missing" in detail["message"] or "场景二" in detail["message"]


def test_create_import_job_rejects_scene_folder_without_videos(
    tmp_path: Path,
) -> None:
    """import 模式选择无受支持视频的场景文件夹应返回具体名称。"""
    _configure_scene_folders(
        tmp_path,
        [("空场景", "scenes/empty"), ("有效场景", "scenes/valid")],
        with_videos=False,
    )
    # Only the valid folder gets a video
    (tmp_path / "workspace" / "scenes" / "valid" / "clip.mp4").write_bytes(
        b"fake video content"
    )
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "文案",
            "scene_folder_ids": ["scenes/empty"],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "SCENE_MEDIA_MISSING"
    assert "空场景" in detail["message"]


def test_create_import_job_accepts_valid_scene_folders(tmp_path: Path) -> None:
    """import 模式选择有效场景文件夹后创建成功。"""
    _configure_scene_folders(
        tmp_path,
        [("场景一", "scenes/one"), ("场景二", "scenes/two")],
    )
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "文案",
            "scene_folder_ids": ["scenes/one", "scenes/two"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scene_folder_ids"] == ["scenes/one", "scenes/two"]
    assert data["phase"] == "queued"

    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{data['job_id']}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    assert raw["scene_folder_ids"] == ["scenes/one", "scenes/two"]


def test_create_import_job_persists_scene_folder_ids(tmp_path: Path) -> None:
    """单次 create_job 将 scene_folder_ids 写入 JobRecord。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "文案",
            "scene_folder_ids": ["scenes/one"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scene_folder_ids"] == ["scenes/one"]


def test_create_generate_job_ignores_scene_folder_ids(tmp_path: Path) -> None:
    """generate 模式创建 Job 时 scene_folder_ids 可选且不校验。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "generate",
        },
    )
    assert resp.status_code == 200


def test_batch_create_import_jobs_rejects_invalid_scene_folders(
    tmp_path: Path,
) -> None:
    """批量 import 创建时任一 Job 场景文件夹无效即整批拒绝。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "jobs": [
                {
                    "name": "有效",
                    "mode": "import",
                    "manual_script": "文案",
                    "scene_folder_ids": ["scenes/one"],
                },
                {
                    "name": "无效",
                    "mode": "import",
                    "manual_script": "文案",
                    "scene_folder_ids": ["scenes/missing"],
                },
            ],
        },
    )
    assert resp.status_code == 400


def test_batch_create_import_jobs_persists_scene_folder_ids(
    tmp_path: Path,
) -> None:
    """批量 import 创建时 scene_folder_ids 持久化到每个 JobRecord。"""
    _configure_scene_folders(
        tmp_path, [("场景一", "scenes/one"), ("场景二", "scenes/two")]
    )
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "jobs": [
                {
                    "name": "第一个",
                    "mode": "import",
                    "manual_script": "文案1",
                    "scene_folder_ids": ["scenes/one"],
                },
                {
                    "name": "第二个",
                    "mode": "import",
                    "manual_script": "文案2",
                    "scene_folder_ids": ["scenes/two"],
                },
            ],
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["scene_folder_ids"] == ["scenes/one"]
    assert results[1]["scene_folder_ids"] == ["scenes/two"]

    for r, expected in zip(results, ["scenes/one", "scenes/two"]):
        job_path = (
            tmp_path
            / "workspace"
            / "projects"
            / "prj_001"
            / "control"
            / "jobs"
            / f"{r['job_id']}.json"
        )
        raw = json.loads(job_path.read_text(encoding="utf-8"))
        assert raw["scene_folder_ids"] == [expected]


def test_old_incomplete_import_job_moves_to_migration_required(
    tmp_path: Path,
) -> None:
    """存量未完成 import Job（无 scene_folder_ids）被 tick 进入 migration_required。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "文案",
            "scene_folder_ids": ["scenes/one"],
        },
    ).json()
    job_id = created["job_id"]

    # Simulate legacy job without scene_folder_ids by editing disk directly
    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{job_id}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    raw.pop("scene_folder_ids", None)
    job_path.write_text(json.dumps(raw), encoding="utf-8")

    # Directly invoke the tick service to observe migration_required transition
    from packages.file_store.repository import FileStoreRepository
    from packages.pipeline_services.job_tick_service import JobTickService
    from apps.control_plane.app import create_orchestrator

    repo = FileStoreRepository(tmp_path)
    orchestrator = create_orchestrator(tmp_path, client.app.state.config_reader)
    svc = JobTickService(
        orchestrator, repo, config_reader=client.app.state.config_reader
    )
    summary = svc.tick(
        "prj_001",
        job_id,
        "test",
        root_dir=tmp_path,
        project_dir=tmp_path / "workspace" / "projects" / "prj_001",
    )
    assert summary.to_phase == "migration_required"

    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["phase"] == "migration_required"


# ── 存量 Job 场景迁移 ──────────────────────────────────────────────


def test_migrate_scenes_endpoint_rejects_invalid_folders(tmp_path: Path) -> None:
    """迁移端点拒绝无效的场景文件夹。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "文案",
            "scene_folder_ids": ["scenes/one"],
        },
    ).json()
    job_id = created["job_id"]

    # Force migration_required state
    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{job_id}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    raw["phase"] = "migration_required"
    job_path.write_text(json.dumps(raw), encoding="utf-8")

    resp = client.post(
        f"/api/jobs/{job_id}/migrate-scenes",
        json={"scene_folder_ids": ["scenes/missing"]},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] in {
        "SCENE_FOLDER_NOT_FOUND",
        "SCENE_FOLDER_NOT_CONFIGURED",
    }


def test_migrate_scenes_endpoint_preserves_config_and_resets_to_queued(
    tmp_path: Path,
) -> None:
    """补选场景后保留文案等配置，清理旧产物，phase 回到 queued。"""
    _configure_scene_folders(
        tmp_path, [("场景一", "scenes/one"), ("场景二", "scenes/two")]
    )
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "保留文案",
            "tts_voice": "冰糖",
            "language": "cantonese",
            "scene_folder_ids": ["scenes/one"],
        },
    ).json()
    job_id = created["job_id"]

    job_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / f"{job_id}.json"
    )
    raw = json.loads(job_path.read_text(encoding="utf-8"))
    raw["phase"] = "migration_required"
    raw["execution"] = {
        "status": "failed",
        "current_attempt": 1,
        "max_attempts": 3,
        "error": {
            "code": "SCENE_INPUT_MISSING",
            "message": "missing",
            "retryable": False,
        },
    }
    raw["artifacts"] = [
        {"kind": "old", "relative_path": "old.mp4", "url": "", "active": False}
    ]
    job_path.write_text(json.dumps(raw), encoding="utf-8")

    runtime_dir = (
        tmp_path / "workspace" / "projects" / "prj_001" / "runtime" / "jobs" / job_id
    )
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "old.mp4").write_bytes(b"old artifact")

    resp = client.post(
        f"/api/jobs/{job_id}/migrate-scenes",
        json={"scene_folder_ids": ["scenes/two"]},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "migrated"
    assert resp.json()["phase"] == "queued"

    saved = json.loads(job_path.read_text(encoding="utf-8"))
    assert saved["phase"] == "queued"
    assert saved["scene_folder_ids"] == ["scenes/two"]
    assert saved["manual_script"] == "保留文案"
    assert saved["tts_voice"] == "冰糖"
    assert saved["language"] == "cantonese"
    assert saved["artifacts"] == []
    assert saved["execution"]["status"] == "pending"
    assert not (runtime_dir / "old.mp4").exists()


def test_migrate_scenes_endpoint_rejects_non_migration_job(
    tmp_path: Path,
) -> None:
    """只有处于 migration_required 的 Job 才能调用迁移端点。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    created = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "文案",
            "scene_folder_ids": ["scenes/one"],
        },
    ).json()
    job_id = created["job_id"]

    resp = client.post(
        f"/api/jobs/{job_id}/migrate-scenes",
        json={"scene_folder_ids": ["scenes/one"]},
    )
    assert resp.status_code == 409


def test_list_scene_folders_returns_configured_folders(tmp_path: Path) -> None:
    """GET /api/scene-folders 返回配置的场景文件夹列表。"""
    _configure_scene_folders(
        tmp_path, [("场景一", "scenes/one"), ("场景二", "scenes/two")]
    )
    client = _make_client(tmp_path)
    resp = client.get("/api/scene-folders")
    assert resp.status_code == 200
    data = resp.json()
    assert data["folders"] == [
        {"name": "场景一", "path": "scenes/one"},
        {"name": "场景二", "path": "scenes/two"},
    ]


# ── 批量创建预校验 ────────────────────────────────────────────────


def test_batch_create_validates_all_before_persisting(tmp_path: Path) -> None:
    """批量创建先校验所有条目再落盘，任一条目失败则 0 创建。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)

    jobs_control_dir = (
        tmp_path / "workspace" / "projects" / "prj_001" / "control" / "jobs"
    )
    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "jobs": [
                {
                    "name": "有效条目",
                    "mode": "import",
                    "manual_script": "文案",
                    "scene_folder_ids": ["scenes/one"],
                },
                {
                    "name": "无效条目",
                    "mode": "import",
                    "manual_script": "文案",
                    "scene_folder_ids": ["scenes/missing"],
                },
            ],
        },
    )
    assert resp.status_code == 400

    # 确认 0 个 Job 文件落盘
    job_files = (
        list(jobs_control_dir.glob("*.json")) if jobs_control_dir.exists() else []
    )
    assert len(job_files) == 0


def test_batch_create_error_includes_item_index(tmp_path: Path) -> None:
    """批量创建验证失败时返回具体条目索引和名称。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)

    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "jobs": [
                {
                    "name": "条目A",
                    "mode": "import",
                    "manual_script": "文案",
                    "scene_folder_ids": ["scenes/one"],
                },
                {
                    "name": "条目B",
                    "mode": "import",
                    "manual_script": "文案",
                    "scene_folder_ids": ["scenes/one"],
                },
                {
                    "name": "条目C",
                    "mode": "import",
                    "manual_script": "文案",
                    "scene_folder_ids": [],
                },
            ],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    # 应包含条目索引信息
    assert "errors" in detail
    errors = detail["errors"]
    assert len(errors) >= 1
    # 第一个（也是唯一的）错误应指向第 3 个条目 (index 2)
    assert errors[0]["index"] == 2
    assert "条目C" in errors[0]["item_name"]
    assert errors[0]["error"]["code"] == "SCENE_INPUT_MISSING"


def test_batch_create_with_multiple_errors_reports_first(tmp_path: Path) -> None:
    """批量创建多条目失败时报告第一个失败条目的具体信息。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)

    resp = client.post(
        "/api/projects/prj_001/jobs/batch",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "jobs": [
                {
                    "name": "条目1",
                    "mode": "import",
                    "manual_script": "文案",
                    "scene_folder_ids": [],
                },
                {
                    "name": "条目2",
                    "mode": "import",
                    "manual_script": "文案",
                    "scene_folder_ids": ["scenes/missing"],
                },
            ],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "BATCH_VALIDATION_FAILED"
    # message 应提及第一个失败的条目
    assert "条目1" in detail["message"] or "第 1" in detail["message"]


def test_create_import_job_rejects_not_configured_scene_folder(
    tmp_path: Path,
) -> None:
    """单次 import 创建 Job 时未配置的场景文件夹路径返回 SCENE_FOLDER_NOT_CONFIGURED。"""
    _configure_scene_folders(tmp_path, [("场景一", "scenes/one")])
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "文案",
            "scene_folder_ids": ["scenes/not_configured"],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "SCENE_FOLDER_NOT_CONFIGURED"
    assert "scenes/not_configured" in detail["message"]
