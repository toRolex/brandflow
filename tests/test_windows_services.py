import re
import subprocess
from pathlib import Path


WINDOWS_DIR = Path(__file__).parents[1] / "packaging" / "windows"
REPO_ROOT = WINDOWS_DIR.parents[1]
RUNTIME_PRESERVE_FILE = WINDOWS_DIR / "runtime-preserve-patterns.txt"


def _git_clean_excludes() -> list[str]:
    return [
        line.strip()
        for line in RUNTIME_PRESERVE_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _git_clean_args() -> list[str]:
    return [
        "-fd",
        *[arg for pattern in _git_clean_excludes() for arg in ("-e", pattern)],
    ]


def _assert_git_clean_preserves_runtime_state(
    tmp_path: Path, clean_args: list[str]
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(
        (REPO_ROOT / ".gitignore").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    runtime_paths = (
        ".env",
        ".env.production",
        ".runtime_batch_direction.txt",
        "config/app_config.json",
        "config/projects/product-1/voice_clone_sample.mp3",
        "config/providers.yaml",
        "config/templates/custom.json",
        "data/metrics.db",
        "frontend/node_modules/package/index.js",
        "knowledge/documents.json",
        "logs/control-plane.log",
        ".node/node-v20.18.3-win-x64/node.exe",
        ".uv-python/cpython-3.11/python.exe",
        ".venv/Scripts/python.exe",
        "packaging/windows/progress.json",
        "reports/metrics.json",
        "schedule.db",
        "tools/models/model.bin",
        "worker_workspace/jobs/job.json",
        "workspace/projects/project-1/control/jobs/job-1.json",
    )
    for relative_path in runtime_paths:
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime state", encoding="utf-8")

    stale_source = tmp_path / "stale-source.py"
    stale_source.write_text("remove me", encoding="utf-8")

    subprocess.run(["git", "clean", *clean_args], cwd=tmp_path, check=True)

    assert not stale_source.exists(), "untracked source residue should still be cleaned"
    for relative_path in runtime_paths:
        assert (tmp_path / relative_path).exists(), (
            f"deployment cleanup deleted runtime state: {relative_path}"
        )


def test_git_clean_excludes_use_forward_slashes() -> None:
    """``git clean -e`` takes gitignore patterns, where ``\\`` is an escape char.

    ``config\\app_config.json`` therefore matches nothing, so the whole untracked
    ``config/`` directory is wiped along with app_config.json and providers.yaml.
    """
    excludes = _git_clean_excludes()
    assert excludes, "deploy.bat should still run git clean with excludes"

    for pattern in excludes:
        assert "\\" not in pattern, (
            f"exclude pattern {pattern!r} uses a backslash; gitignore patterns "
            "require '/' or the exclusion silently fails"
        )


def test_git_clean_preserves_runtime_state() -> None:
    excludes = _git_clean_excludes()
    for required in (
        "config",
        "data",
        "knowledge",
        "workspace",
        "frontend/node_modules",
    ):
        assert required in excludes, f"cleanup must exclude {required}"


def test_runtime_preservation_manifest_protects_all_known_state(
    tmp_path: Path,
) -> None:
    _assert_git_clean_preserves_runtime_state(tmp_path, _git_clean_args())


def test_deploy_and_rollback_share_runtime_preservation_manifest() -> None:
    deploy = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")
    rollback = (WINDOWS_DIR / "rollback-prod.ps1").read_text(encoding="utf-8")

    assert "runtime-preserve-patterns.txt" in deploy
    assert "git clean -fd !GIT_CLEAN_EXCLUDES!" in deploy
    assert "runtime-preserve-patterns.txt" in rollback
    assert '@("clean", "-fd")' in rollback
    assert "git clean -fdx" not in deploy
    assert '"-fdx"' not in rollback


def test_deploy_uses_control_plane_as_only_pipeline_executor() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    assert "AppEnvironmentExtra" in content
    assert "DEV_AUTO_TICK=1" in content
    assert "stop brandflow-worker" not in content
    assert "brandflow-worker start= disabled" not in content


def test_deploy_builds_python311_venv_outside_the_live_environment() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")
    excludes = _git_clean_excludes()

    assert 'set "PYTHON_VERSION=3.11"' in content
    assert 'set "UV_PYTHON_INSTALL_DIR=%PROJECT_DIR%\\.uv-python"' in content
    assert 'set "STAGED_VENV=%PROJECT_DIR%\\.venv-deploy"' in content
    assert 'set "BACKUP_VENV=%PROJECT_DIR%\\.venv-backup-%RANDOM%-%RANDOM%"' in content
    for required in (".venv-deploy", ".venv-backup-*", ".uv-python"):
        assert required in excludes
    assert "uv python install !PYTHON_VERSION!" in content
    assert "uv python find --managed-python --system !PYTHON_VERSION!" in content
    assert "Path(sys.executable).resolve().is_relative_to" in content
    assert 'uv venv --relocatable --python "!DEPLOY_PYTHON!"' in content
    assert 'uv sync --python "!DEPLOY_PYTHON!" --all-extras --dev' in content


def test_deploy_uses_project_local_node20_for_frontend_builds() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    assert 'set "NODE_VERSION=20.18.3"' in content
    assert 'set "NODE_ROOT=%PROJECT_DIR%\\.node"' in content
    assert ".node" in _git_clean_excludes()
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


def test_cd_checkout_fails_instead_of_overwriting_untracked_runtime_state() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")
    cd_block = content[content.index("if defined RUNNER_SRC (") :]
    cd_block = cd_block[: cd_block.index(") else (")]

    assert "git reset --hard HEAD" not in content
    assert "git diff --quiet --ignore-submodules --" in content
    assert "git diff --cached --quiet --ignore-submodules --" in content
    assert "git checkout -f" not in cd_block
    assert "git checkout --no-overwrite-ignore -B %BRANCH% FETCH_HEAD" in cd_block


def test_rollback_fails_instead_of_overwriting_runtime_state() -> None:
    content = (WINDOWS_DIR / "rollback-prod.ps1").read_text(encoding="utf-8")

    assert '@("reset", "--hard", "HEAD")' not in content
    assert "& git status --porcelain --untracked-files=no" in content
    assert re.search(r'"checkout",\s*"--no-overwrite-ignore",\s*"FETCH_HEAD"', content)


def test_rollback_bootstraps_pinned_corepack_without_disabling_integrity() -> None:
    content = (WINDOWS_DIR / "rollback-prod.ps1").read_text(encoding="utf-8")

    assert '"corepack@0.31.0"' in content
    assert '"pnpm@11.17.0"' in content
    assert '"--ignore-scripts"' in content
    assert "COREPACK_INTEGRITY_KEYS" not in content


def test_deploy_only_stops_control_plane_for_atomic_venv_cutover() -> None:
    content = (WINDOWS_DIR / "deploy.bat").read_text(encoding="utf-8")

    sync_position = content.index(
        'uv sync --python "!DEPLOY_PYTHON!" --all-extras --dev'
    )
    stop_position = content.index("sc.exe stop brandflow-control-plane")
    cutover_position = content.index(
        'call :move_venv_with_retry "!STAGED_VENV!" "!LIVE_VENV!" 10'
    )
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
    assert 'findstr /R /C:": *4 "' in content
    assert 'findstr /R /C:": *!EXPECTED_STATE_NUMBER! "' in content
    assert 'findstr /C:"RUNNING"' not in content
    assert "call :grant_runner_service_control" in content
    assert "grant-service-control.request" in content
    assert "'http://127.0.0.1:17890/api/update'" in content
    assert "show-latest-asgi-error.ps1" in content
    assert (
        "if !errorlevel! neq 0 ("
        in content[
            stop_position : content.index("call :wait_for_service_state", stop_position)
        ]
    )
    assert "call :rollback_venv" in content


def test_service_control_failure_diagnostic_is_bounded_to_latest_asgi_error() -> None:
    script = (WINDOWS_DIR / "show-latest-asgi-error.ps1").read_text(encoding="utf-8")

    assert "Get-Content -LiteralPath $LogPath -Tail 400" in script
    assert '"ERROR:.*ASGI application"' in script
    assert "$errorStart + 99" in script


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
