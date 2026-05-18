from __future__ import annotations

import requests


class WorkerHttpClient:
    def __init__(
        self,
        base_url: str,
        worker_id: str,
        worker_version: str,
        capabilities: list[str],
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.worker_id = worker_id
        self.worker_version = worker_version
        self.capabilities = capabilities

    def _absolute_url(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("/"):
            return f"{self.base_url}{url}"
        return f"{self.base_url}/{url}"

    def poll(self) -> dict:
        response = requests.post(
            f"{self.base_url}/workers/poll",
            json={
                "worker_id": self.worker_id,
                "worker_version": self.worker_version,
                "capabilities": self.capabilities,
                "current_tasks": [],
                "free_slots": 1,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def download_input_bundle(self, bundle_url: str) -> dict:
        response = requests.get(
            self._absolute_url(bundle_url),
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def upload_artifacts(self, task_id: str, files: list[dict]) -> None:
        response = requests.post(
            f"{self.base_url}/workers/tasks/{task_id}/artifacts",
            json={"files": files},
            timeout=30,
        )
        response.raise_for_status()

    def report(self, payload: dict) -> None:
        response = requests.post(
            f"{self.base_url}/workers/tasks/{payload['task_id']}/report",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
