from pathlib import Path


WINDOWS_DIR = Path(__file__).parents[1] / "packaging" / "windows"


def test_deploy_uses_control_plane_as_only_pipeline_executor() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    assert "AppEnvironmentExtra DEV_AUTO_TICK=1" in content
    assert "stop brandflow-worker" in content
    assert "brandflow-worker start= disabled" in content


def test_start_and_stop_only_manage_control_plane() -> None:
    for script in ("start.bat", "stop.bat"):
        content = (WINDOWS_DIR / script).read_text(encoding="utf-8")
        assert "brandflow-control-plane" in content
        assert "brandflow-worker" not in content
