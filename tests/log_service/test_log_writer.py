import json
from pathlib import Path

from packages.log_service.log_writer import log_error


def test_log_error_appends_a_timestamped_json_record(tmp_path: Path) -> None:
    log_file = log_error(
        {"source": "backend", "level": "error", "message": "broken"},
        log_dir=tmp_path / "logs",
    )

    record = json.loads(log_file.read_text(encoding="utf-8"))
    assert record["message"] == "broken"
    assert record["timestamp"]
