import json
import sys
from pathlib import Path

from packages.log_service.excepthook import install_global_excepthook


def test_excepthook_logs_and_delegates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("packages.log_service.log_writer.get_log_dir", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: calls.append(args))
    install_global_excepthook()
    error = ValueError("uncaught")
    sys.excepthook(type(error), error, error.__traceback__)
    assert calls
    assert (
        json.loads(next(tmp_path.glob("*.jsonl")).read_text())["message"] == "uncaught"
    )
