import json
from pathlib import Path
from typing import Any

from apps.runtime_worker.http_client import WorkerHttpClient
from apps.runtime_worker.loop import WorkerLoop


class StubIdleApi:
    def __init__(self) -> None:
        self.poll_calls = 0

    def poll(self) -> dict:
        self.poll_calls += 1
        return {"command": "idle", "next_poll_after_seconds": 5}


class StubApi:
    def __init__(self) -> None:
        self.reports: list[dict] = []
        self.uploads: list[tuple[str, list[dict]]] = []
        self.download_requests: list[str] = []

    def poll(self) -> dict:
        return {
            "command": "run_task",
            "project_id": "project-001",
            "job_id": "job-001",
            "task_id": "task-001",
            "task_type": "run_phase",
            "lease_id": "lease-001",
            "attempt_id": "attempt-001",
            "lease_expires_at": "2026-05-18T12:00:00Z",
            "input_bundle_url": "/bundle",
            "report_url": "/report",
            "heartbeat_url": "/heartbeat",
            "expected_outputs": ["script", "audio", "subtitles", "final_video"],
            "runtime_limits": {"max_seconds": 60},
        }

    def download_input_bundle(self, bundle_url: str) -> dict:
        self.download_requests.append(bundle_url)
        assert bundle_url == "/bundle"
        return {"project_id": "project-001", "job_id": "job-001"}

    def upload_artifacts(self, task_id: str, files: list[dict]) -> None:
        self.uploads.append((task_id, files))

    def report(self, payload: dict) -> None:
        self.reports.append(payload)


class SpyScriptBridge:
    def __init__(self) -> None:
        self.generate_calls: list[dict] = []

    def generate(self, product: str, output_dir: Path, mock: bool) -> dict[str, Any]:
        self.generate_calls.append({"product": product, "output_dir": str(output_dir), "mock": mock})
        txt_path = output_dir / "stub_script.txt"
        json_path = output_dir / "stub_script.json"
        txt_path.write_text("测试文案 stub\n", encoding="utf-8")
        json_path.write_text('{"final_script": "测试文案 stub"}\n', encoding="utf-8")
        return {"txt_path": str(txt_path), "json_path": str(json_path), "final_script": "测试文案 stub"}


class SpyMediaBridge:
    def __init__(self) -> None:
        self.tts_calls: list[dict] = []
        self.build_base_video_calls: list[dict] = []

    def synthesize_tts(self, script_text: str, output_path: Path) -> Path:
        self.tts_calls.append({"script_text": script_text, "output_path": str(output_path)})
        output_path.write_bytes(b"\x00" * 128)
        return output_path

    def build_script_timed_srt(self, audio_path: Path, srt_path: Path, script_text: str) -> None:
        srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试文案 stub\n", encoding="utf-8")

    def build_base_video(self, project_dir: Path, job_payload: dict[str, Any], output_path: Path) -> None:
        self.build_base_video_calls.append({"project_dir": str(project_dir), "output_path": str(output_path)})
        output_path.write_bytes(b"\x00" * 256)

    def burn_final_video(
        self,
        base_video_path: Path,
        audio_path: Path,
        srt_path: Path,
        final_video_path: Path,
        cover_clip_path: Path | None,
    ) -> None:
        final_video_path.write_bytes(b"\x00" * 512)


StubScriptBridge = SpyScriptBridge
StubMediaBridge = SpyMediaBridge


class StubApiWithManualInputs:
    def __init__(self, manual_script: str = "", uploaded_audio_path: str = "") -> None:
        self.reports: list[dict] = []
        self.uploads: list[tuple[str, list[dict]]] = []
        self.download_requests: list[str] = []
        self.manual_script = manual_script
        self.uploaded_audio_path = uploaded_audio_path

    def poll(self) -> dict:
        return {
            "command": "run_task",
            "project_id": "project-001",
            "job_id": "job-001",
            "task_id": "task-001",
            "task_type": "run_phase",
            "lease_id": "lease-001",
            "attempt_id": "attempt-001",
            "lease_expires_at": "2026-05-18T12:00:00Z",
            "input_bundle_url": "/bundle",
            "report_url": "/report",
            "heartbeat_url": "/heartbeat",
            "expected_outputs": ["script", "audio", "subtitles", "final_video"],
            "runtime_limits": {"max_seconds": 60},
            "manual_script": self.manual_script,
            "uploaded_audio_path": self.uploaded_audio_path,
        }

    def download_input_bundle(self, bundle_url: str) -> dict:
        self.download_requests.append(bundle_url)
        return {"project_id": "project-001", "job_id": "job-001"}

    def upload_artifacts(self, task_id: str, files: list[dict]) -> None:
        self.uploads.append((task_id, files))

    def report(self, payload: dict) -> None:
        self.reports.append(payload)

    def burn_final_video(
        self,
        base_video_path: Path,
        audio_path: Path,
        srt_path: Path,
        final_video_path: Path,
        cover_clip_path: Path | None,
    ) -> None:
        final_video_path.write_bytes(b"\x00" * 512)


class StubScheduleBridge:
    def add(self, job_id: str, platform: str, title: str = "", description: str = "") -> int:
        return 1


def test_http_client_absolute_url_handles_absolute_and_relative_paths() -> None:
    client = WorkerHttpClient(
        base_url="http://127.0.0.1:17890",
        worker_id="worker-mac",
        worker_version="0.1.0",
        capabilities=["mac-local"],
    )

    assert client._absolute_url("http://example.com/bundle") == "http://example.com/bundle"
    assert client._absolute_url("https://example.com/bundle") == "https://example.com/bundle"
    assert client._absolute_url("/bundle") == "http://127.0.0.1:17890/bundle"
    assert client._absolute_url("bundle") == "http://127.0.0.1:17890/bundle"


def test_worker_loop_returns_immediately_for_idle_command(tmp_path: Path) -> None:
    api = StubIdleApi()
    loop = WorkerLoop(
        api=api,
        worker_id="worker-mac",
        workspace_root=tmp_path,
        script_bridge=StubScriptBridge(),
        media_bridge=StubMediaBridge(),
        schedule_bridge=StubScheduleBridge(),
    )

    loop.run_once()

    assert api.poll_calls == 1
    assert not (tmp_path / "attempts").exists()


def test_worker_loop_reports_success_and_uploads_artifacts(tmp_path: Path) -> None:
    api = StubApi()
    loop = WorkerLoop(
        api=api,
        worker_id="worker-mac",
        workspace_root=tmp_path,
        script_bridge=StubScriptBridge(),
        media_bridge=StubMediaBridge(),
        schedule_bridge=StubScheduleBridge(),
    )

    loop.run_once()

    attempt_root = tmp_path / "attempts" / "attempt-001"
    assert attempt_root.exists()
    assert api.download_requests == ["/bundle"]
    assert api.uploads[0][0] == "task-001"
    assert api.uploads[0][1]
    assert api.reports[0]["status"] == "succeeded"
    assert api.reports[0]["attempt_id"] == "attempt-001"
    assert api.reports[0]["started_at"] <= api.reports[0]["finished_at"]


def test_worker_loop_uses_shared_vertical_assembler_for_selected_clips(tmp_path: Path, monkeypatch) -> None:
    clip_a = tmp_path / "clip_a.mp4"
    clip_b = tmp_path / "clip_b.mp4"
    clip_a.write_bytes(b"a")
    clip_b.write_bytes(b"b")

    class SemanticPathApi(StubApi):
        def download_input_bundle(self, bundle_url: str) -> dict:
            payload = super().download_input_bundle(bundle_url)
            job_dir = tmp_path / "attempts" / "attempt-001" / "output"
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "selected_clips.json").write_text(
                json.dumps(
                    [
                        {"file_path": str(clip_a)},
                        {"file_path": str(clip_b)},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return payload

    api = SemanticPathApi()
    spy_media = SpyMediaBridge()

    loop = WorkerLoop(
        api=api,
        worker_id="worker-mac",
        workspace_root=tmp_path,
        script_bridge=StubScriptBridge(),
        media_bridge=spy_media,
        schedule_bridge=StubScheduleBridge(),
    )
    monkeypatch.setattr(loop.adapter, "ensure_tools", lambda: None)
    monkeypatch.setattr(loop.adapter, "attempt_root", lambda workspace_root, attempt_id: workspace_root / "attempts" / attempt_id)

    loop.run_once()

    assert len(spy_media.build_base_video_calls) == 1
    job_payload = spy_media.build_base_video_calls[0]
    expected_project_dir = tmp_path.resolve() / "projects" / "project-001"
    assert job_payload["project_dir"] == str(expected_project_dir)


def test_worker_loop_skips_llm_when_manual_script_provided(tmp_path: Path) -> None:
    manual_script = "这是手动输入的测试文案，用于验证跳过LLM生成功能。"
    api = StubApiWithManualInputs(manual_script=manual_script)
    spy_script = SpyScriptBridge()
    spy_media = SpyMediaBridge()
    loop = WorkerLoop(
        api=api,
        worker_id="worker-mac",
        workspace_root=tmp_path,
        script_bridge=spy_script,
        media_bridge=spy_media,
        schedule_bridge=StubScheduleBridge(),
    )

    loop.run_once()

    assert len(spy_script.generate_calls) == 0, f"LLM should be skipped but was called {len(spy_script.generate_calls)} times"
    assert len(spy_media.tts_calls) == 1
    assert spy_media.tts_calls[0]["script_text"] == manual_script


def test_worker_loop_skips_tts_when_audio_uploaded(tmp_path: Path) -> None:
    audio_dir = tmp_path / "uploaded"
    audio_dir.mkdir()
    fake_audio = audio_dir / "my_audio.mp3"
    fake_audio.write_bytes(b"\x00" * 256)

    api = StubApiWithManualInputs(uploaded_audio_path=str(fake_audio))
    spy_script = SpyScriptBridge()
    spy_media = SpyMediaBridge()
    loop = WorkerLoop(
        api=api,
        worker_id="worker-mac",
        workspace_root=tmp_path,
        script_bridge=spy_script,
        media_bridge=spy_media,
        schedule_bridge=StubScheduleBridge(),
    )

    loop.run_once()

    assert len(spy_script.generate_calls) == 1, "LLM should be called when no manual script"
    assert len(spy_media.tts_calls) == 0, f"TTS should be skipped but was called {len(spy_media.tts_calls)} times"


def test_worker_loop_skips_both_when_manual_script_and_audio_provided(tmp_path: Path) -> None:
    audio_dir = tmp_path / "uploaded"
    audio_dir.mkdir()
    fake_audio = audio_dir / "my_audio.mp3"
    fake_audio.write_bytes(b"\x00" * 256)

    manual_script = "手动输入的文案"
    api = StubApiWithManualInputs(manual_script=manual_script, uploaded_audio_path=str(fake_audio))
    spy_script = SpyScriptBridge()
    spy_media = SpyMediaBridge()
    loop = WorkerLoop(
        api=api,
        worker_id="worker-mac",
        workspace_root=tmp_path,
        script_bridge=spy_script,
        media_bridge=spy_media,
        schedule_bridge=StubScheduleBridge(),
    )

    loop.run_once()

    assert len(spy_script.generate_calls) == 0, f"LLM should be skipped but was called {len(spy_script.generate_calls)} times"
    assert len(spy_media.tts_calls) == 0, f"TTS should be skipped but was called {len(spy_media.tts_calls)} times"
