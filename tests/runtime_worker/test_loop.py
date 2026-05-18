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


class StubScriptBridge:
    def generate(self, product: str, output_dir: Path, mock: bool) -> dict[str, Any]:
        txt_path = output_dir / "stub_script.txt"
        json_path = output_dir / "stub_script.json"
        txt_path.write_text("测试文案 stub\n", encoding="utf-8")
        json_path.write_text('{"final_script": "测试文案 stub"}\n', encoding="utf-8")
        return {"txt_path": str(txt_path), "json_path": str(json_path), "final_script": "测试文案 stub"}


class StubMediaBridge:
    def synthesize_tts(self, script_text: str, output_path: Path) -> Path:
        output_path.write_bytes(b"\x00" * 128)
        return output_path

    def build_script_timed_srt(self, audio_path: Path, srt_path: Path, script_text: str) -> None:
        srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试文案 stub\n", encoding="utf-8")


class StubScheduleBridge:
    def append(self, project_name: str, job_payload: dict[str, Any], final_video_path: Path) -> None:
        pass


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
