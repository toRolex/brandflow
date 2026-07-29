from pathlib import Path


WINDOWS_DIR = Path(__file__).parents[1] / "packaging" / "windows"


def test_deploy_uses_control_plane_as_only_pipeline_executor() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    assert "AppEnvironmentExtra" in content
    assert "DEV_AUTO_TICK=1" in content
    assert "stop brandflow-worker" in content
    assert "brandflow-worker start= disabled" in content


def test_deploy_builds_python311_venv_outside_the_live_environment() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    assert 'set "PYTHON_VERSION=3.11"' in content
    assert 'set "UV_PYTHON_INSTALL_DIR=%PROJECT_DIR%\\.uv-python"' in content
    assert 'set "STAGED_VENV=%PROJECT_DIR%\\.venv-deploy"' in content
    assert 'set "BACKUP_VENV=%PROJECT_DIR%\\.venv-backup-%RANDOM%-%RANDOM%"' in content
    assert "-e .venv-deploy -e .venv-backup-* -e .uv-python" in content
    assert "uv python install !PYTHON_VERSION!" in content
    assert "uv python find --managed-python --system !PYTHON_VERSION!" in content
    assert "Path(sys.executable).resolve().is_relative_to" in content
    assert 'uv venv --relocatable --python "!DEPLOY_PYTHON!"' in content
    assert 'uv sync --python "!DEPLOY_PYTHON!" --all-extras --dev' in content


def test_deploy_uses_project_local_node20_for_frontend_builds() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    assert 'set "NODE_VERSION=20.18.3"' in content
    assert 'set "NODE_ROOT=%PROJECT_DIR%\\.node"' in content
    assert "-e .node" in content
    assert "node-v!NODE_VERSION!-win-x64.zip" in content
    assert "Expand-Archive" in content
    assert 'set "PATH=!NODE_DIR!;!PATH!"' in content
    assert "process.version === 'v!NODE_VERSION!' ? 0 : 1" in content
    assert "process.version !==" not in content
    assert '"!NODE_DIR!\\node.exe" --version' in content
    assert 'if exist "C:\\Program Files\\nodejs\\node.exe"' not in content


def test_cd_deploy_fetches_from_checked_out_runner_without_second_network_call() -> (
    None
):
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")
    cd_block = content[content.index("if defined RUNNER_SRC (") :]
    cd_block = cd_block[: cd_block.index(") else (")]

    assert 'git fetch --no-tags --update-shallow "%RUNNER_SRC%" HEAD' in cd_block
    assert "git fetch --tags origin" not in cd_block


def test_deploy_only_stops_control_plane_for_atomic_venv_cutover() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    sync_position = content.index(
        'uv sync --python "!DEPLOY_PYTHON!" --all-extras --dev'
    )
    stop_position = content.index("sc.exe stop brandflow-control-plane")
    cutover_position = content.index('move /y "!STAGED_VENV!" "!LIVE_VENV!"')
    start_position = content.index(
        "sc.exe start brandflow-control-plane", cutover_position
    )

    backup_cleanup_position = content.index(
        'if exist "!BACKUP_VENV!" rmdir /s /q "!BACKUP_VENV!"'
    )

    assert sync_position < stop_position < cutover_position < start_position
    assert start_position < backup_cleanup_position
    assert 'call :move_venv_with_retry "!LIVE_VENV!" "!BACKUP_VENV!" 30' in content
    assert "for /L %%M in (1,1,!MOVE_ATTEMPTS!) do (" in content
    assert "call :get_control_plane_state" in content
    assert "Get-Service -Name 'brandflow-control-plane'" in content
    assert 'findstr /C:"RUNNING"' not in content
    assert "call :grant_runner_service_control" in content
    assert "grant-service-control.request" in content
    assert "'http://127.0.0.1:17890/api/update'" in content
    assert (
        "if !errorlevel! neq 0 ("
        in content[
            stop_position : content.index("call :wait_for_service_state", stop_position)
        ]
    )
    assert "call :rollback_venv" in content


def test_deploy_only_reconfigures_a_new_service() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")
    new_service_block = content[content.index('if "!SERVICE_EXISTED!"=="0" (') :]
    new_service_block = new_service_block[
        : new_service_block.index("sc.exe start brandflow-control-plane")
    ]

    assert "nssm install brandflow-control-plane" in new_service_block
    assert "call :configure_service" in new_service_block


def test_deploy_rollback_checks_each_destructive_step() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")
    rollback = content[content.rindex("\n:rollback_venv") :]

    assert 'set "ROLLBACK_FAILED=0"' in rollback
    assert 'if exist "!LIVE_VENV!" set "ROLLBACK_FAILED=1"' in rollback
    assert 'if exist "!BACKUP_VENV!" set "ROLLBACK_FAILED=1"' in rollback
    assert "call :wait_for_service_state RUNNING 30" in rollback
    assert "自动回滚失败" in rollback
    assert 'if "!ROLLBACK_FAILED!"=="1"' in rollback
    assert "exit /b 1" in rollback


def test_deploy_service_executes_the_project_venv_python_directly() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    assert (
        "nssm install brandflow-control-plane "
        '"%PROJECT_DIR%\\.venv\\Scripts\\python.exe"' in content
    )
    assert '/v Application /d "%PROJECT_DIR%\\.venv\\Scripts\\python.exe"' in content
    assert '/v AppParameters /d "-m apps.control_plane"' in content
    assert 'cmd /c "uv run' not in content


def test_deploy_health_check_requires_the_checked_out_version() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    assert 'set "EXPECTED_VERSION="' in content
    assert "data.get('status') == 'ok'" in content
    assert "data.get('version') == '!EXPECTED_VERSION!'" in content
    assert "运行版本不是 !EXPECTED_VERSION!" in content


def test_start_and_stop_only_manage_control_plane() -> None:
    for script in ("start.bat", "stop.bat"):
        content = (WINDOWS_DIR / script).read_text(encoding="utf-8")
        assert "brandflow-control-plane" in content
        assert "brandflow-worker" not in content
