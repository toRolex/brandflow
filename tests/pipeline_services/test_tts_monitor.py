from datetime import datetime
from packages.pipeline_services.tts_monitor import (
    TTSRequestLog,
    TTSMetrics,
    TTSMonitor,
)


class TestTTSRequestLog:
    def test_create_log(self):
        log = TTSRequestLog(
            id="req_001",
            task_id="task_001",
            project_id="proj_001",
            timestamp=datetime.now(),
            model="mimo-v2.5-tts",
            voice_id="Mia",
            style_prompt="自然",
            text_length=100,
            success=True,
            audio_duration_ms=3200,
            latency_ms=1800,
            error_type=None,
            error_message=None,
            attempt_count=1,
            final_voice_id="Mia"
        )
        assert log.id == "req_001"
        assert log.success is True
        assert log.audio_duration_ms == 3200

    def test_to_dict(self):
        log = TTSRequestLog(
            id="req_001",
            task_id="task_001",
            project_id="proj_001",
            timestamp=datetime(2025, 6, 1, 12, 0, 0),
            model="mimo-v2.5-tts",
            voice_id="Mia",
            style_prompt="自然",
            text_length=100,
            success=True,
            audio_duration_ms=3200,
            latency_ms=1800,
            error_type=None,
            error_message=None,
            attempt_count=1,
            final_voice_id="Mia"
        )
        data = log.to_dict()
        assert isinstance(data, dict)
        assert data["id"] == "req_001"
        assert data["timestamp"] == "2025-06-01T12:00:00"


class TestTTSMetrics:
    def test_default_metrics(self):
        metrics = TTSMetrics(time_range="24h")
        assert metrics.total_requests == 0
        assert metrics.success_count == 0
        assert metrics.failure_count == 0
        assert metrics.success_rate == 0.0

    def test_calculate_success_rate(self):
        metrics = TTSMetrics(
            time_range="24h",
            total_requests=100,
            success_count=95,
            failure_count=5
        )
        assert metrics.success_rate == 0.95


class TestTTSMonitor:
    def test_record_request(self, tmp_path):
        monitor = TTSMonitor(log_dir=str(tmp_path))
        log = TTSRequestLog(
            id="req_001",
            task_id="task_001",
            project_id="proj_001",
            timestamp=datetime.now(),
            model="mimo-v2.5-tts",
            voice_id="Mia",
            style_prompt="自然",
            text_length=100,
            success=True,
            audio_duration_ms=3200,
            latency_ms=1800,
            error_type=None,
            error_message=None,
            attempt_count=1,
            final_voice_id="Mia"
        )
        monitor.record_request(log)
        assert len(monitor.get_logs()) == 1

    def test_get_metrics(self, tmp_path):
        monitor = TTSMonitor(log_dir=str(tmp_path))

        for i in range(10):
            log = TTSRequestLog(
                id=f"req_{i:03d}",
                task_id=f"task_{i:03d}",
                project_id="proj_001",
                timestamp=datetime.now(),
                model="mimo-v2.5-tts",
                voice_id="Mia",
                style_prompt="自然",
                text_length=100,
                success=i < 8,
                audio_duration_ms=3200 if i < 8 else None,
                latency_ms=1800,
                error_type="rate_limit" if i >= 8 else None,
                error_message="429" if i >= 8 else None,
                attempt_count=1,
                final_voice_id="Mia"
            )
            monitor.record_request(log)

        metrics = monitor.get_metrics()
        assert metrics.total_requests == 10
        assert metrics.success_count == 8
        assert metrics.failure_count == 2
        assert metrics.success_rate == 0.8

    def test_get_logs_with_filter(self, tmp_path):
        monitor = TTSMonitor(log_dir=str(tmp_path))

        success_log = TTSRequestLog(
            id="req_001", task_id="t1", project_id="p1",
            timestamp=datetime.now(), model="mimo-v2.5-tts",
            voice_id="Mia", style_prompt="自然", text_length=100,
            success=True, audio_duration_ms=3200, latency_ms=1800,
            error_type=None, error_message=None,
            attempt_count=1, final_voice_id="Mia"
        )
        fail_log = TTSRequestLog(
            id="req_002", task_id="t2", project_id="p1",
            timestamp=datetime.now(), model="mimo-v2.5-tts",
            voice_id="Mia", style_prompt="自然", text_length=100,
            success=False, audio_duration_ms=None, latency_ms=5000,
            error_type="timeout", error_message="request timeout",
            attempt_count=3, final_voice_id="Mia"
        )

        monitor.record_request(success_log)
        monitor.record_request(fail_log)

        all_logs = monitor.get_logs()
        assert len(all_logs) == 2

        failed_logs = monitor.get_logs(status="failed")
        assert len(failed_logs) == 1
        assert failed_logs[0].id == "req_002"
