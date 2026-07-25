import json
from pathlib import Path

from packages.log_service.log_writer import get_log_dir, log_error


def test_log_error_appends_a_timestamped_json_record(tmp_path: Path) -> None:
    log_file = log_error(
        {"source": "backend", "level": "error", "message": "broken"},
        log_dir=tmp_path / "logs",
    )

    record = json.loads(log_file.read_text(encoding="utf-8"))
    assert record["message"] == "broken"
    assert record["timestamp"]


def test_log_directory_uses_non_roaming_application_data(monkeypatch) -> None:
    calls: list[dict] = []

    def user_data_dir(*_args, **kwargs):
        calls.append(kwargs)
        return "C:/Users/test/AppData/Local/brandflow"

    monkeypatch.setattr("packages.log_service.log_writer.user_data_dir", user_data_dir)

    assert get_log_dir() == Path("C:/Users/test/AppData/Local/brandflow/logs")
    assert calls == [{"appauthor": False}]
