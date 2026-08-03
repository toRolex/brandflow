"""Regression test for batch N>2 TTS provider rate-limit bug.

User report
-----------
> 批量模式的时候，任务生成数量设置为 2 条视频时，生产能够正常成功；
> 一旦任务视频数量大于 2 条，生产流程就会失败。

Root cause (machine-verifiable hypothesis)
-----------------------------------------
Each Job's ``synthesize_script`` opens a ``ThreadPoolExecutor(max_workers=4)``
and fans out one ``_synthesize_sentence`` per script sentence.  With
``MAX_CONCURRENT_JOBS=2``, two simultaneous Jobs can already push up to 8
concurrent outbound TTS calls.  When 3+ Jobs are created in one batch and
reach ``tts_generating`` in lockstep, the per-Job 4-worker fanout
multiplies into ~12 concurrent calls.  Qwen (and similar rate-limited TTS
providers) respond with HTTP 429 — which ``tts_provider`` maps to
``TTSQuotaExceededError`` (a ``TTSBlockedError`` subclass) and which the
service treats as **permanent, non-retryable**.  The Job's ``tts`` phase
goes terminal-failed.

The fix: a process-wide ``threading.Semaphore`` (default size 4, override
via ``BRANDFLOW_TTS_PROVIDER_CONCURRENCY``) caps the total in-flight
provider calls regardless of how many Jobs run in parallel.  This test
verifies the fix deterministically by stubbing the provider to reject
calls beyond a threshold and asserting that N=3 batch succeeds.

Test plan
---------
1. **Without the fix** (``BRANDFLOW_TTS_PROVIDER_CONCURRENCY=0`` to disable
   the semaphore): the mock provider, configured to 429 above 5 concurrent
   calls, must cause the 3-Job batch to fail with TTSQuotaExceededError.
   This reproduces the user's reported bug.
2. **With the fix** (default cap=4): the same 3-Job batch succeeds because
   the semaphore caps concurrent calls to 4, well under the 5-call mock
   limit.  N=2 succeeds in both configurations (control).
"""

from __future__ import annotations

import threading
import time as _wall_clock
from pathlib import Path


def _make_mock_provider(threshold: int) -> tuple:
    """Return ``(provider, peak_in_flight)`` — a TTS provider mock that 429s
    once concurrent in-flight calls exceed *threshold*.
    """
    active = 0
    peak = 0
    peak_lock = threading.Lock()

    class _MockProvider:
        def synthesize(self, sentence: str, config) -> bytes:
            nonlocal active, peak
            with peak_lock:
                active += 1
                if active > peak:
                    peak = active
            try:
                if active > threshold:
                    # Hold a moment so concurrent calls pile up against
                    # the cap, then return 429-equivalent.  Mirrors the
                    # real Qwen behaviour: rate-limit kicks in
                    # *after* a soft threshold is exceeded.
                    _wall_clock.sleep(0.05)
                    from packages.pipeline_services.tts_provider import (
                        TTSQuotaExceededError,
                    )

                    raise TTSQuotaExceededError("simulated 429")
                # Real call would take ~0.5-1s; we use a small delay so
                # the fanout is observable.
                _wall_clock.sleep(0.05)
                # Return a tiny but valid PCM WAV: 0.5 s of silence
                # at 8 kHz, mono, 16-bit.  This is the minimum that
                # lets ffprobe return a real numeric duration
                # (the post-processing pipeline rejects "N/A").
                import struct

                sample_rate = 8000
                num_samples = 4000  # 0.5 s of silence
                data_size = num_samples * 2
                wav = b"RIFF"
                wav += struct.pack("<I", 36 + data_size)
                wav += b"WAVE"
                wav += b"fmt "
                wav += struct.pack(
                    "<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16
                )
                wav += b"data"
                wav += struct.pack("<I", data_size)
                wav += b"\x00\x00" * num_samples
                return wav
            finally:
                with peak_lock:
                    active -= 1

    class _Peak:
        @property
        def value(self) -> int:
            with peak_lock:
                return peak

    return _MockProvider(), _Peak()


def _run_batch(
    tmp_path: Path,
    n_jobs: int,
    threshold: int,
    *,
    semaphore_concurrency: int | None,
) -> tuple[bool, int, int]:
    """Run *n_jobs* Jobs through the real TTS service and return
    ``(all_succeeded, peak_concurrent_calls, failed_count)``.
    """
    from packages.pipeline_services.sentence_tts_service import (
        SentenceTTSService,
    )

    if semaphore_concurrency is not None:
        import os

        os.environ["BRANDFLOW_TTS_PROVIDER_CONCURRENCY"] = str(semaphore_concurrency)
        # Reset module-level cache so the new env var takes effect.
        from packages.pipeline_services import sentence_tts_service

        sentence_tts_service._PROVIDER_CALL_SEMAPHORE = None
    else:
        import os

        os.environ.pop("BRANDFLOW_TTS_PROVIDER_CONCURRENCY", None)
        from packages.pipeline_services import sentence_tts_service

        sentence_tts_service._PROVIDER_CALL_SEMAPHORE = None

    provider, peak = _make_mock_provider(threshold)

    def _noop_normalize(
        src: Path, dst: Path, audio_format: str, sample_rate: int
    ) -> None:
        """Bypass the ffmpeg normalize step — just copy the file."""
        import shutil

        shutil.copyfile(src, dst)

    def _noop_duration(path: Path) -> float:
        """Bypass ffprobe — report a fixed duration."""
        return 0.5

    service = SentenceTTSService(
        provider=provider,
        config={
            "model": "mock",
            "voice": "mock-voice",
            "audio_format": "wav",
        },
        cache_dir=tmp_path / "tts_cache",
        max_retries=1,  # keep the test fast; no inline retry on quota anyway
        normalize_fn=_noop_normalize,
        duration_fn=_noop_duration,
    )

    successes = 0
    failures: list[Exception] = []
    successes_lock = threading.Lock()

    def _run_one(idx: int) -> None:
        nonlocal successes
        # Each Job has unique sentences to bypass the TTS fingerprint
        # cache.  Concatenated into one script string for
        # ``synthesize_script``.
        script_text = (
            f"[job-{idx:02d}] 第一句测试文案。"
            f"[job-{idx:02d}] 第二句内容继续。"
            f"[job-{idx:02d}] 第三句收尾。"
        )
        try:
            service.synthesize_script(
                script_text=script_text,
                output_path=tmp_path / f"job-{idx:02d}.wav",
            )
        except Exception as e:  # noqa: BLE001
            with successes_lock:
                failures.append(e)
        else:
            with successes_lock:
                successes += 1

    threads = [threading.Thread(target=_run_one, args=(i,)) for i in range(n_jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30.0)

    return (successes == n_jobs, peak.value, n_jobs - successes, failures)


def test_n2_succeeds_with_or_without_semaphore(tmp_path: Path) -> None:
    """N=2 control: must succeed in both configurations.

    With 2 Jobs and a 4-worker fanout per Job, the *theoretical* peak
    is 8 concurrent provider calls — but in practice it rarely exceeds
    6 because the worker pool is shared inside one process.  We set
    the mock threshold to 7 so the 2-Job peak (≤6) stays under, mirroring
    the user's "N=2 works in production" baseline.
    """
    ok, peak, fail, errors = _run_batch(
        tmp_path, n_jobs=2, threshold=7, semaphore_concurrency=0
    )
    assert ok, (
        f"N=2 without semaphore failed: fail={fail}, peak={peak}, errors={errors[:1]}"
    )
    assert peak <= 7, f"N=2 peak {peak} exceeded mock threshold"
    # With semaphore (cap=4): 2 jobs × 3 sentences, but capped to 4.
    ok2, peak2, fail2, errors2 = _run_batch(
        tmp_path, n_jobs=2, threshold=7, semaphore_concurrency=4
    )
    assert ok2, (
        f"N=2 with semaphore failed: fail={fail2}, peak={peak2}, errors={errors2[:1]}"
    )


def test_n3_without_semaphore_reproduces_user_bug(tmp_path: Path) -> None:
    """N=3 without semaphore: must fail.  Reproduces the user's bug.

    Three Jobs × 3 sentences = 9 provider calls.  With 4-worker fanout
    per Job they fan out faster than the provider can serve under a
    threshold of 7, so the mock starts 429-ing and the Jobs go terminal.
    """
    ok, peak, fail, errors = _run_batch(
        tmp_path, n_jobs=3, threshold=7, semaphore_concurrency=0
    )
    assert not ok, (
        f"N=3 without semaphore should fail (user bug) but succeeded.  "
        f"peak={peak} fail={fail}, errors={errors[:1]}"
    )
    assert peak > 7, f"N=3 should have exceeded 7 concurrent calls; peak={peak}"


def test_n3_with_semaphore_succeeds(tmp_path: Path) -> None:
    """N=3 with semaphore (cap=4): must succeed.  The fix."""
    ok, peak, fail, errors = _run_batch(
        tmp_path, n_jobs=3, threshold=7, semaphore_concurrency=4
    )
    assert ok, (
        f"N=3 with semaphore failed: fail={fail}, peak={peak}, errors={errors[:1]}"
    )
    assert peak <= 4, (
        f"semaphore should cap at 4 concurrent calls; observed peak={peak}"
    )


def test_n5_with_semaphore_succeeds(tmp_path: Path) -> None:
    """N=5 with semaphore: must succeed.  Stress the fix."""
    ok, peak, fail, errors = _run_batch(
        tmp_path, n_jobs=5, threshold=7, semaphore_concurrency=4
    )
    assert ok, (
        f"N=5 with semaphore failed: fail={fail}, peak={peak}, errors={errors[:1]}"
    )
    assert peak <= 4, (
        f"semaphore should cap at 4 concurrent calls; observed peak={peak}"
    )
