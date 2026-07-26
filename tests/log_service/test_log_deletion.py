"""Tests for log_deletion service — single / batch / cleanup with today-protection,
date validation, lock safety, and file-not-found idempotency (#354).
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from packages.log_service import log_deletion
from packages.log_service.log_writer import _LOG_LOCK


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d


def _write_log_file(log_dir: Path, date_str: str, content: str = "{}") -> Path:
    """Create a minimal JSONL log file for *date_str*."""
    file = log_dir / f"{date_str}.jsonl"
    file.write_text(content + "\n", encoding="utf-8")
    return file


# ── helpers ──────────────────────────────────────────────────────────────────


def test_is_valid_calendar_date_rejects_bad_format() -> None:
    assert not log_deletion._is_valid_calendar_date("2026-07-2")  # single digit
    assert not log_deletion._is_valid_calendar_date("2026/07/25")
    assert not log_deletion._is_valid_calendar_date("not-a-date")


def test_is_valid_calendar_date_rejects_fake_date() -> None:
    assert not log_deletion._is_valid_calendar_date("2026-02-30")


def test_is_valid_calendar_date_accepts_real_date() -> None:
    assert log_deletion._is_valid_calendar_date("2026-07-25")


# ── delete_single ────────────────────────────────────────────────────────────


def test_delete_single_success(log_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(log_deletion, "get_log_dir", lambda: log_dir)
    _write_log_file(log_dir, "2025-12-01")
    result = log_deletion.delete_single("2025-12-01")
    assert result == {"date": "2025-12-01", "deleted": True}
    assert not (log_dir / "2025-12-01.jsonl").exists()


def test_delete_single_not_found_idempotent(log_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(log_deletion, "get_log_dir", lambda: log_dir)
    result = log_deletion.delete_single("2025-12-01")
    assert result == {"date": "2025-12-01", "deleted": False}


# ── delete_batch ─────────────────────────────────────────────────────────────


def test_delete_batch_mixed(log_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(log_deletion, "get_log_dir", lambda: log_dir)
    _write_log_file(log_dir, "2025-12-01")
    _write_log_file(log_dir, "2025-12-02")

    today_str = log_deletion._today_str()
    result = log_deletion.delete_batch(
        ["2025-12-01", "2025-12-02", "2025-12-99", today_str]
    )
    assert set(result["deleted"]) == {"2025-12-01", "2025-12-02"}
    assert set(result["not_found"]) == {"2025-12-99"}
    assert set(result["protected"]) == {today_str}


def test_delete_batch_handles_invalid_date_format(log_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(log_deletion, "get_log_dir", lambda: log_dir)
    result = log_deletion.delete_batch(["2026-02-30", "not-a-date"])
    assert "2026-02-30" in result["not_found"]
    assert "not-a-date" in result["not_found"]


# ── cleanup ──────────────────────────────────────────────────────────────────


def test_cleanup_rejects_zero_and_negative() -> None:
    with pytest.raises(ValueError, match="before_days must be >= 1"):
        log_deletion.cleanup(0)
    with pytest.raises(ValueError, match="before_days must be >= 1"):
        log_deletion.cleanup(-1)


def test_cleanup_deletes_strictly_before_cutoff(log_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(log_deletion, "get_log_dir", lambda: log_dir)

    today_str = log_deletion._today_str()
    today_date = date.fromisoformat(today_str)
    day_before = (today_date - timedelta(days=1)).isoformat()
    two_days_before = (today_date - timedelta(days=2)).isoformat()

    _write_log_file(log_dir, two_days_before)
    _write_log_file(log_dir, day_before)
    _write_log_file(log_dir, today_str)

    result = log_deletion.cleanup(before_days=1)
    # Cutoff = today - 1 day → strictly before yesterday.
    # day_before is yesterday, NOT strictly before cutoff → kept
    # two_days_before IS before cutoff → deleted
    assert result["deleted_count"] == 1
    assert two_days_before in result["deleted"]
    assert day_before not in result["deleted"]
    assert today_str not in result["deleted"]


def test_cleanup_with_before_days_7(log_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(log_deletion, "get_log_dir", lambda: log_dir)

    today_str = log_deletion._today_str()
    today_date = date.fromisoformat(today_str)
    old_date = (today_date - timedelta(days=8)).isoformat()
    recent_date = (today_date - timedelta(days=6)).isoformat()

    _write_log_file(log_dir, old_date)
    _write_log_file(log_dir, recent_date)
    _write_log_file(log_dir, today_str)

    result = log_deletion.cleanup(before_days=7)
    # Cutoff = today - 7.  old_date (8 days ago) < cutoff → deleted
    assert result["deleted_count"] == 1
    assert old_date in result["deleted"]
    assert recent_date not in result["deleted"]
    assert today_str not in result["deleted"]


def test_cleanup_empty_dir(log_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(log_deletion, "get_log_dir", lambda: log_dir)
    result = log_deletion.cleanup(before_days=3)
    assert result == {"deleted": [], "deleted_count": 0}


# ── lock safety ──────────────────────────────────────────────────────────────


def test_delete_uses_writer_lock(log_dir: Path, monkeypatch) -> None:
    """Verify that _delete_file_safe acquires _LOG_LOCK — the same lock the
    writer uses — so concurrent write + delete cannot race."""
    monkeypatch.setattr(log_deletion, "get_log_dir", lambda: log_dir)
    _write_log_file(log_dir, "2025-12-01")

    # Acquire the lock ourselves, then try to delete in a background thread.
    # The delete should block until we release the lock.
    import threading

    acquired = threading.Event()
    result_holder: list[dict] = []

    def _try_delete() -> None:
        result_holder.append(log_deletion.delete_single("2025-12-01"))

    with _LOG_LOCK:
        t = threading.Thread(target=_try_delete, daemon=True)
        t.start()
        t.join(timeout=0.3)  # Give the thread time to reach the lock
        # Thread should still be blocked on the lock
        assert t.is_alive(), "delete should block behind _LOG_LOCK"

    # Now the lock is released; the delete thread should finish
    t.join(timeout=2)
    assert not t.is_alive()
    assert result_holder == [{
        "date": "2025-12-01",
        "deleted": True,
    }]
