from __future__ import annotations

from pathlib import Path
from typing import Any

from main_controller import ScheduleWriter


class LegacyScheduleBridge:
    def __init__(self, workbook_path: Path) -> None:
        self.writer = ScheduleWriter(workbook_path)

    def append(self, project_name: str, job_payload: dict[str, Any], final_video_path: Path) -> None:
        self.writer.append(project_name, job_payload, final_video_path)
