from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _make_client(tmp_path: Path):
    return TestClient(create_app(tmp_path))


# ── 手动脚本更新不影响模式路由 ────────────────────────────────────


def test_update_manual_script_preserves_import_mode(tmp_path: Path) -> None:
    """修改 manual_script 后，import 模式任务仍保持 import 模式。"""
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/projects/prj_001/jobs",
        json={
            "product": "test",
            "platforms": ["douyin"],
            "mode": "import",
            "manual_script": "初始文案",
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
