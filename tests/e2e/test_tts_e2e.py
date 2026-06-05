"""端到端测试：使用Playwright测试完整用户流程"""

import subprocess
import pytest


class TestTTSEndToEnd:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.browser_opened = False
        yield
        if self.browser_opened:
            subprocess.run(["playwright-cli", "close"], capture_output=True)

    def _open_browser(self, url):
        subprocess.run(["playwright-cli", "open", url], capture_output=True)
        self.browser_opened = True

    def _take_snapshot(self):
        result = subprocess.run(
            ["playwright-cli", "snapshot"],
            capture_output=True, text=True
        )
        return result.stdout

    def _click_element(self, ref):
        subprocess.run(["playwright-cli", "click", ref], capture_output=True)

    def _fill_input(self, ref, value):
        subprocess.run(["playwright-cli", "fill", ref, value], capture_output=True)

    def _navigate(self, url):
        subprocess.run(["playwright-cli", "goto", url], capture_output=True)

    @pytest.mark.e2e
    def test_tts_config_page_loads(self):
        self._open_browser("http://localhost:17890/tts-config")
        snapshot = self._take_snapshot()
        assert "TTS 配置" in snapshot or "tts-config" in snapshot.lower()

    @pytest.mark.e2e
    def test_tts_monitor_page_loads(self):
        self._open_browser("http://localhost:17890")
        self._navigate("http://localhost:17890/tts-monitor")
        snapshot = self._take_snapshot()
        assert "TTS 监控" in snapshot or "tts-monitor" in snapshot.lower()

    @pytest.mark.e2e
    def test_tts_config_model_selection(self):
        self._open_browser("http://localhost:17890/tts-config")
        snapshot = self._take_snapshot()
        assert "预置音色" in snapshot
        assert "音色设计" in snapshot

    @pytest.mark.e2e
    def test_tts_config_voice_selection(self):
        self._open_browser("http://localhost:17890/tts-config")
        self._click_element("e16")
        snapshot = self._take_snapshot()
        assert "主音色" in snapshot
        assert "备用音色" in snapshot

    @pytest.mark.e2e
    def test_tts_config_style_presets(self):
        self._open_browser("http://localhost:17890/tts-config")
        snapshot = self._take_snapshot()
        assert "自然口播" in snapshot
        assert "热情推荐" in snapshot

    @pytest.mark.e2e
    def test_tts_monitor_metrics_display(self):
        self._open_browser("http://localhost:17890/tts-monitor")
        snapshot = self._take_snapshot()
        assert "总请求" in snapshot
        assert "成功率" in snapshot
        assert "平均延迟" in snapshot

    @pytest.mark.e2e
    def test_tts_monitor_time_range_selector(self):
        self._open_browser("http://localhost:17890/tts-monitor")
        snapshot = self._take_snapshot()
        assert "1小时" in snapshot
        assert "24小时" in snapshot
        assert "7天" in snapshot
