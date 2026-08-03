@echo off
echo Begin deploy.bat
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 一键部署

:: CD 场景下 GITHUB_WORKSPACE 是 runner 的临时目录（每次 job 重建），不是生产数据目录。
:: 这里默认走 D:\brandflow（持续服务所在），把最新代码同步过去后再启动。
set "PROJECT_DIR=D:\brandflow"
if not "%GITHUB_WORKSPACE%"=="" set "RUNNER_SRC=%GITHUB_WORKSPACE%"
set "BRANCH=%~1"
if "%BRANCH%"=="" set "BRANCH=main"
set "PYTHON_VERSION=3.11"
set "UV_PYTHON_INSTALL_DIR=%PROJECT_DIR%\.uv-python"
set "LIVE_VENV=%PROJECT_DIR%\.venv"
set "STAGED_VENV=%PROJECT_DIR%\.venv-deploy"
set "BACKUP_VENV=%PROJECT_DIR%\.venv-backup-%RANDOM%-%RANDOM%"
set "NODE_VERSION=20.18.3"
set "NODE_ROOT=%PROJECT_DIR%\.node"
set "NODE_DIR=%NODE_ROOT%\node-v%NODE_VERSION%-win-x64"
set "RUNTIME_PRESERVE_FILE=%~dp0runtime-preserve-patterns.txt"

:: Debug headers — 方便排查 CD 失败
echo === Brandflow deploy entrypoint ===
echo BRANCH       = %BRANCH%
echo PROJECT_DIR  = %PROJECT_DIR%
echo CWD          = %CD%
echo RUNNER_SRC   = %RUNNER_SRC%
echo --- workspace contents ---
if exist "%PROJECT_DIR%" (dir /b "%PROJECT_DIR%" | findstr /R /C:"packaging" /C:"frontend" /C:"apps" /C:"packages" /C:".git")
echo === end headers ===
echo.

:: 自动提权（CD 场景跳过；GitHub Actions runner 已是高权限 SYSTEM/管理员）
if "%GITHUB_ACTIONS%"=="" (
    net session >nul 2>&1
    if !errorlevel! neq 0 (
        echo 请求管理员权限...
        powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\" %BRANCH%' -Verb RunAs"
        exit /b
    )
)

if not exist "%PROJECT_DIR%" (
    echo [warn] 项目目录 %PROJECT_DIR% 不存在 — 自动创建（初次部署）
    mkdir "%PROJECT_DIR%"
)

set "LOG_FILE=%PROJECT_DIR%\logs\deploy.log"
if not exist "%PROJECT_DIR%\logs\" mkdir "%PROJECT_DIR%\logs\"

echo ============================================
echo  Brandflow 一键部署
echo ============================================
echo  项目: %PROJECT_DIR%
echo  日志: !LOG_FILE!
echo ============================================
echo.

echo [%date% %time%] ========== 部署开始 ========== >> "!LOG_FILE!"

:: ============================================
:: Step 1: 前置工具（幂等，缺啥装啥）
:: ============================================
echo [1/7] 检查前置工具 ...

where uv >nul 2>&1 || (
    echo   - 安装 uv ...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
)
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if exist "C:\Users\ziyua\.local\bin\uv.exe" set "PATH=C:\Users\ziyua\.local\bin;%PATH%"
if exist "C:\Users\admin\.local\bin\uv.exe" set "PATH=C:\Users\admin\.local\bin;%PATH%"

if not exist "!NODE_DIR!\node.exe" (
    echo   - 安装项目共享的 Node.js !NODE_VERSION! ...
    if not exist "!NODE_ROOT!" mkdir "!NODE_ROOT!"
    if exist "!NODE_DIR!" rmdir /s /q "!NODE_DIR!"
    set "NODE_ARCHIVE=%TEMP%\brandflow-node-v!NODE_VERSION!-!RANDOM!.zip"
    curl.exe -fSL "https://nodejs.org/dist/v!NODE_VERSION!/node-v!NODE_VERSION!-win-x64.zip" -o "!NODE_ARCHIVE!"
    if !errorlevel! neq 0 (
        echo [错误] Node.js !NODE_VERSION! 下载失败 >> "!LOG_FILE!"
        if exist "!NODE_ARCHIVE!" del /q "!NODE_ARCHIVE!"
        if "%GITHUB_ACTIONS%"=="" pause
        exit /b 1
    )
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '!NODE_ARCHIVE!' -DestinationPath '!NODE_ROOT!' -Force"
    set "NODE_INSTALL_EXIT=!errorlevel!"
    if exist "!NODE_ARCHIVE!" del /q "!NODE_ARCHIVE!"
    if !NODE_INSTALL_EXIT! neq 0 (
        echo [错误] Node.js !NODE_VERSION! 解压失败 >> "!LOG_FILE!"
        if "%GITHUB_ACTIONS%"=="" pause
        exit /b 1
    )
)

if not exist "!NODE_DIR!\node.exe" (
    echo [错误] Node.js 安装后仍不可用 >> "!LOG_FILE!"
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)
set "PATH=!NODE_DIR!;!PATH!"
"!NODE_DIR!\node.exe" -e "process.exit(process.version === 'v!NODE_VERSION!' ? 0 : 1)"
if !errorlevel! neq 0 (
    echo [错误] 项目 Node.js 版本不是 v!NODE_VERSION! >> "!LOG_FILE!"
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)
echo   - Node:
"!NODE_DIR!\node.exe" --version

where pnpm >nul 2>&1 || (
    if exist "%USERPROFILE%\AppData\Local\pnpm\bin\pnpm.CMD" (
        set "PATH=%USERPROFILE%\AppData\Local\pnpm\bin;%PATH%"
    ) else (
        echo   - 安装 pnpm ...
        powershell -ExecutionPolicy Bypass -Command "iwr https://get.pnpm.io/install.ps1 -useb | iex"
        if exist "%USERPROFILE%\AppData\Local\pnpm\bin\pnpm.CMD" set "PATH=%USERPROFILE%\AppData\Local\pnpm\bin;%PATH%"
    )
)

where ffmpeg >nul 2>&1 || (
    echo   - 安装 FFmpeg ...
    winget install --id Gyan.FFmpeg -e --silent --accept-package-agreements
)

where nssm >nul 2>&1 || (
    echo   - 安装 NSSM ...
    winget install NSSM -e --silent --accept-package-agreements
)

echo   工具就绪。

:: ============================================
:: Step 2: 初始化目录 + .env
:: ============================================
echo [2/7] 初始化项目目录 ...
if not exist "%PROJECT_DIR%\config" mkdir "%PROJECT_DIR%\config"
if not exist "%PROJECT_DIR%\config\templates" mkdir "%PROJECT_DIR%\config\templates"
if not exist "%PROJECT_DIR%\workspace" mkdir "%PROJECT_DIR%\workspace"
if not exist "%PROJECT_DIR%\data" mkdir "%PROJECT_DIR%\data"
if not exist "%PROJECT_DIR%\knowledge" mkdir "%PROJECT_DIR%\knowledge"

if not exist "%PROJECT_DIR%\.env" (
    if exist "%PROJECT_DIR%\.env.example" (
        echo   .env 不存在，从 .env.example 复制 ...
        copy "%PROJECT_DIR%\.env.example" "%PROJECT_DIR%\.env" >nul
        echo   已生成 .env 模板，请编辑填入 API Key 后再启动。
    )
)
echo   目录已确认。

:: ============================================
:: Step 3: 同步最新代码（目标分支 = %BRANCH%）
:: GitHub Actions runner 源在 %GITHUB_WORKSPACE%，先把它复制到 %PROJECT_DIR%
:: ============================================
echo [3/7] 同步最新代码 (分支: %BRANCH%) ...

:: Git 安全目录：本进程 NETWORK SERVICE 跑在 D:\brandflow 时会被认作 dubious ownership
git config --global --add safe.directory "*" >nul 2>&1

if not exist "%PROJECT_DIR%\.git" (
    if exist "%PROJECT_DIR%" (
        :: 目录存在但没 .git，先 init
        pushd "%PROJECT_DIR%"
        git init >nul 2>&1
        git remote add origin https://github.com/toRolex/brandflow.git >nul 2>&1
        popd
    ) else (
        mkdir "%PROJECT_DIR%"
        pushd "%PROJECT_DIR%"
        git init
        git remote add origin https://github.com/toRolex/brandflow.git
        popd
    )
)

pushd "%PROJECT_DIR%"

:: 生产目录如有 tracked 本地修改则安全停止；部署不得静默覆盖机器状态。
git diff --quiet --ignore-submodules --
if errorlevel 1 (
    echo [错误] 生产目录存在 tracked 本地修改或无法检查工作区，拒绝覆盖 >> "!LOG_FILE!"
    popd
    exit /b 1
)
git diff --cached --quiet --ignore-submodules --
if errorlevel 1 (
    echo [错误] 生产目录存在 staged 本地修改或无法检查索引，拒绝覆盖 >> "!LOG_FILE!"
    popd
    exit /b 1
)

:: CD：从 runner workspace 同步代码到持久目录（保留 .venv/.env/workspace 等）
if defined RUNNER_SRC (
    echo   CD 模式：从 runner workspace 同步代码 ...
    git remote set-url origin https://github.com/toRolex/brandflow.git >nul 2>&1
    :: actions/checkout 已取得精确提交；从本地 runner repo fetch，避免重复访问 GitHub。
    git fetch --no-tags --update-shallow "%RUNNER_SRC%" HEAD
    if errorlevel 1 (
        echo [错误] 从 runner workspace 同步代码失败 >> "!LOG_FILE!"
        popd
        pause
        exit /b 1
    )
    :: 不使用 -f：如果新代码与机器运行时文件冲突，应安全失败而不是覆盖数据。
    git checkout --no-overwrite-ignore -B %BRANCH% FETCH_HEAD
    if errorlevel 1 (
        echo [错误] git checkout FETCH_HEAD 失败 >> "!LOG_FILE!"
        popd
        pause
        exit /b 1
    )
    :: 只清理未跟踪的代码残留；不要使用 -x，否则 .gitignore 中的运行时数据会被删除。
    if not exist "!RUNTIME_PRESERVE_FILE!" (
        echo [错误] 缺少运行时数据保护清单：!RUNTIME_PRESERVE_FILE! >> "!LOG_FILE!"
        popd
        exit /b 1
    )
    set "GIT_CLEAN_EXCLUDES="
    for /F "usebackq delims=" %%E in ("!RUNTIME_PRESERVE_FILE!") do (
        set "GIT_CLEAN_EXCLUDES=!GIT_CLEAN_EXCLUDES! -e %%E"
    )
    git clean -fd !GIT_CLEAN_EXCLUDES! >nul 2>&1
    if errorlevel 1 (
        echo [错误] 清理未跟踪代码残留失败 >> "!LOG_FILE!"
        popd
        exit /b 1
    )
) else (
    echo   手动模式：从 origin 拉取 ...
    git fetch --tags origin
    git checkout %BRANCH%
    if errorlevel 1 (
        echo [错误] git checkout %BRANCH% 失败 >> "!LOG_FILE!"
        popd
        pause
        exit /b 1
    )
    git pull --rebase --autostash
    if errorlevel 1 (
        echo [错误] git pull 失败 >> "!LOG_FILE!"
        popd
        pause
        exit /b 1
    )
)
popd

:: ============================================
:: Step 4: Python 依赖
:: ============================================
echo [4/7] 安装 Python 依赖 ...
pushd "%PROJECT_DIR%"
echo   - 准备项目共享的 CPython !PYTHON_VERSION! ...
uv python install !PYTHON_VERSION!
if !errorlevel! neq 0 (
    set "DEPLOY_EXIT_CODE=!errorlevel!"
    echo [错误] CPython !PYTHON_VERSION! 安装失败 >> "!LOG_FILE!"
    popd
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b !DEPLOY_EXIT_CODE!
)

set "DEPLOY_PYTHON="
for /f "usebackq delims=" %%I in (`uv python find --managed-python --system !PYTHON_VERSION!`) do set "DEPLOY_PYTHON=%%I"
if not defined DEPLOY_PYTHON (
    echo [错误] 找不到项目共享的 CPython !PYTHON_VERSION! >> "!LOG_FILE!"
    popd
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)
"!DEPLOY_PYTHON!" -c "import sys; from pathlib import Path; raise SystemExit(0 if Path(sys.executable).resolve().is_relative_to(Path(r'%UV_PYTHON_INSTALL_DIR%').resolve()) else 1)"
if !errorlevel! neq 0 (
    echo [错误] Python 不在项目共享目录: !DEPLOY_PYTHON! >> "!LOG_FILE!"
    popd
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)
echo   - Python: !DEPLOY_PYTHON!

if exist "!STAGED_VENV!" rmdir /s /q "!STAGED_VENV!"
if exist "!STAGED_VENV!" (
    echo [错误] 无法清理 staging 虚拟环境: !STAGED_VENV! >> "!LOG_FILE!"
    popd
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)

set "UV_PROJECT_ENVIRONMENT=!STAGED_VENV!"
uv venv --relocatable --python "!DEPLOY_PYTHON!" "!STAGED_VENV!"
if !errorlevel! neq 0 (
    echo [错误] staging 虚拟环境创建失败 >> "!LOG_FILE!"
    set "UV_PROJECT_ENVIRONMENT="
    popd
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)
uv sync --python "!DEPLOY_PYTHON!" --all-extras --dev
set "DEPLOY_EXIT_CODE=!errorlevel!"
set "UV_PROJECT_ENVIRONMENT="
if !DEPLOY_EXIT_CODE! neq 0 (
    echo [错误] uv sync 失败 >> "!LOG_FILE!"
    popd
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b !DEPLOY_EXIT_CODE!
)

"!STAGED_VENV!\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
if !errorlevel! neq 0 (
    echo [错误] staging 虚拟环境不是 Python 3.11 >> "!LOG_FILE!"
    popd
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)
popd
echo   Python !PYTHON_VERSION! staging 环境已就绪。

:: ============================================
:: Step 5: 前端编译
:: ============================================
echo [5/7] 编译前端 ...
pushd "%PROJECT_DIR%\frontend"
set "PATH=!NODE_DIR!;!PATH!"
if exist "%USERPROFILE%\AppData\Local\pnpm\bin\pnpm.CMD" set "PATH=%USERPROFILE%\AppData\Local\pnpm\bin;%PATH%"

if not exist "node_modules" (
    call pnpm install --no-frozen-lockfile
    if %errorlevel% neq 0 (
        echo [错误] pnpm install 失败 >> "!LOG_FILE!"
        popd
        pause
        exit /b %errorlevel%
    )
)
call pnpm build
if %errorlevel% neq 0 (
    echo [错误] pnpm build 失败 >> "!LOG_FILE!"
    popd
    pause
    exit /b %errorlevel%
)
popd
echo   前端编译完成。

:: ============================================
:: Step 6: 注册 / 启动服务
:: ============================================
echo [6/7] 原子切换环境并启动服务 ...
set "SERVICE_EXISTED=0"
set "SERVICE_WAS_RUNNING=0"
sc.exe query brandflow-control-plane >nul 2>&1 && set "SERVICE_EXISTED=1"
sc.exe query brandflow-control-plane 2>nul | findstr /R /C:": *4 " >nul && set "SERVICE_WAS_RUNNING=1"
echo   - 服务存在: !SERVICE_EXISTED!，切换前运行中: !SERVICE_WAS_RUNNING!

if "!SERVICE_WAS_RUNNING!"=="1" (
    echo   - 正在停止控制面服务 ...
    sc.exe stop brandflow-control-plane >nul 2>&1
    if !errorlevel! neq 0 (
        echo   - 首次配置 runner 的服务启停权限 ...
        call :grant_runner_service_control
        if !errorlevel! neq 0 (
            echo [错误] 无法为当前 runner 配置控制面服务权限 >> "!LOG_FILE!"
            if "%GITHUB_ACTIONS%"=="" pause
            exit /b 1
        )
        sc.exe stop brandflow-control-plane >nul 2>&1
        if !errorlevel! neq 0 (
            echo [错误] 当前 runner 无法停止控制面服务 >> "!LOG_FILE!"
            if "%GITHUB_ACTIONS%"=="" pause
            exit /b 1
        )
    )
    call :wait_for_service_state STOPPED 30
    if !errorlevel! neq 0 (
        echo [错误] 控制面服务未能在 30 秒内停止 >> "!LOG_FILE!"
        if "%GITHUB_ACTIONS%"=="" pause
        exit /b 1
    )
    echo   - service stopped.
)

if exist "!LIVE_VENV!" (
    call :move_venv_with_retry "!LIVE_VENV!" "!BACKUP_VENV!" 30
    if !errorlevel! neq 0 (
        echo [错误] 控制面停止后等待 30 秒，虚拟环境仍被占用 >> "!LOG_FILE!"
        if "!SERVICE_WAS_RUNNING!"=="1" sc.exe start brandflow-control-plane >nul 2>&1
        if "%GITHUB_ACTIONS%"=="" pause
        exit /b 1
    )
    echo   - live venv backed up.
)

call :move_venv_with_retry "!STAGED_VENV!" "!LIVE_VENV!" 10
if !errorlevel! neq 0 (
    echo [错误] 等待 10 秒后仍无法启用 staging 虚拟环境 >> "!LOG_FILE!"
    call :rollback_venv
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)
echo   - staging venv activated.

if "!SERVICE_EXISTED!"=="0" (
    where nssm >nul 2>&1
    if !errorlevel! neq 0 (
        echo [错误] 首次注册服务需要 nssm，但当前 PATH 中未找到 >> "!LOG_FILE!"
        call :rollback_venv
        if "%GITHUB_ACTIONS%"=="" pause
        exit /b 1
    )
    nssm install brandflow-control-plane "%PROJECT_DIR%\.venv\Scripts\python.exe" "-m apps.control_plane"
    if !errorlevel! neq 0 (
        echo [错误] 注册控制面服务失败 >> "!LOG_FILE!"
        call :rollback_venv
        if "%GITHUB_ACTIONS%"=="" pause
        exit /b 1
    )
    :: NSSM 参数直接写注册表，避免 runner 账户 PATH 中没有 nssm 时无法更新新服务。
    set "SERVICE_PARAMS=HKLM\SYSTEM\CurrentControlSet\Services\brandflow-control-plane\Parameters"
    call :configure_service
    if !errorlevel! neq 0 (
        echo [错误] 更新控制面服务配置失败 >> "!LOG_FILE!"
        call :rollback_venv
        if "%GITHUB_ACTIONS%"=="" pause
        exit /b 1
    )
)

echo   - starting control-plane service ...
sc.exe start brandflow-control-plane
if !errorlevel! neq 0 (
    echo [cutover] control-plane service failed to start
    echo [错误] 控制面服务启动失败 >> "!LOG_FILE!"
    call :rollback_venv
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)

echo   服务已启动。

:: ============================================
:: Step 7: 健康检查
:: ============================================
echo [7/7] 健康检查 ...
set "EXPECTED_VERSION="
set "VERSION_FILE=%TEMP%\brandflow-deploy-version-!RANDOM!.txt"
"!LIVE_VENV!\Scripts\python.exe" -c "import tomllib; print(tomllib.load(open(r'%PROJECT_DIR%\pyproject.toml','rb'))['project']['version'])" > "!VERSION_FILE!"
if !errorlevel! equ 0 set /p EXPECTED_VERSION=<"!VERSION_FILE!"
if exist "!VERSION_FILE!" del /q "!VERSION_FILE!"
if not defined EXPECTED_VERSION (
    echo [错误] 无法读取待部署版本 >> "!LOG_FILE!"
    call :rollback_venv
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)

set "HEALTHY=0"
for /L %%I in (1,1,15) do (
    if "!HEALTHY!"=="0" (
        "!LIVE_VENV!\Scripts\python.exe" -c "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:17890/api/health')); raise SystemExit(0 if data.get('status') == 'ok' and data.get('version') == '!EXPECTED_VERSION!' else 1)" >nul 2>&1 && set "HEALTHY=1"
        if "!HEALTHY!"=="0" powershell -NoProfile -Command "Start-Sleep -Seconds 1"
    )
)
if "!HEALTHY!"=="0" (
    echo [错误] 健康检查失败或运行版本不是 !EXPECTED_VERSION!，请检查日志: !LOG_FILE!
    echo [错误] 新环境健康检查失败，回滚上一环境 >> "!LOG_FILE!"
    call :rollback_venv
    if "%GITHUB_ACTIONS%"=="" pause
    exit /b 1
)

if exist "!BACKUP_VENV!" rmdir /s /q "!BACKUP_VENV!"
if exist "!BACKUP_VENV!" echo [警告] 部署成功，但旧虚拟环境备份未能删除: !BACKUP_VENV! >> "!LOG_FILE!"
echo [%date% %time%] ========== 部署成功 ========== >> "!LOG_FILE!"
echo.
echo ============================================
echo  部署成功
echo  访问: http://127.0.0.1:17890
echo  日志: !LOG_FILE!
echo ============================================
if "%GITHUB_ACTIONS%"=="" pause
exit /b 0

:wait_for_service_state
set "EXPECTED_STATE=%~1"
set "WAIT_SECONDS=%~2"
set "EXPECTED_STATE_NUMBER=4"
if /I "!EXPECTED_STATE!"=="STOPPED" set "EXPECTED_STATE_NUMBER=1"
for /L %%S in (1,1,!WAIT_SECONDS!) do (
    sc.exe query brandflow-control-plane 2>nul | findstr /R /C:": *!EXPECTED_STATE_NUMBER! " >nul && exit /b 0
    powershell -NoProfile -Command "Start-Sleep -Seconds 1"
)
exit /b 1

:grant_runner_service_control
set "SERVICE_CONTROL_REQUEST=%PROJECT_DIR%\packaging\windows\grant-service-control.request"
> "!SERVICE_CONTROL_REQUEST!" echo request
"!STAGED_VENV!\Scripts\python.exe" -c "import urllib.request; request=urllib.request.Request('http://127.0.0.1:17890/api/update', method='POST'); response=urllib.request.urlopen(request, timeout=10); raise SystemExit(0 if response.status == 200 else 1)"
if !errorlevel! neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\packaging\windows\show-latest-asgi-error.ps1"
    exit /b 1
)
for /L %%G in (1,1,15) do (
    if not exist "!SERVICE_CONTROL_REQUEST!" exit /b 0
    powershell -NoProfile -Command "Start-Sleep -Seconds 1"
)
exit /b 1

:move_venv_with_retry
set "MOVE_SOURCE=%~1"
set "MOVE_TARGET=%~2"
set "MOVE_ATTEMPTS=%~3"
for /L %%M in (1,1,!MOVE_ATTEMPTS!) do (
    move /y "!MOVE_SOURCE!" "!MOVE_TARGET!" >nul 2>&1
    if !errorlevel! equ 0 exit /b 0
    powershell -NoProfile -Command "Start-Sleep -Seconds 1"
)
exit /b 1

:rollback_venv
set "ROLLBACK_FAILED=0"
sc.exe query brandflow-control-plane >nul 2>&1
if !errorlevel! equ 0 (
    sc.exe stop brandflow-control-plane >nul 2>&1
    call :wait_for_service_state STOPPED 30 >nul 2>&1
    if !errorlevel! neq 0 set "ROLLBACK_FAILED=1"
)

if "!ROLLBACK_FAILED!"=="0" (
    if exist "!LIVE_VENV!" rmdir /s /q "!LIVE_VENV!"
    if exist "!LIVE_VENV!" set "ROLLBACK_FAILED=1"
)

if "!ROLLBACK_FAILED!"=="0" (
    if exist "!BACKUP_VENV!" move /y "!BACKUP_VENV!" "!LIVE_VENV!" >nul
    if exist "!BACKUP_VENV!" set "ROLLBACK_FAILED=1"
)

if "!SERVICE_WAS_RUNNING!"=="1" if not exist "!LIVE_VENV!\Scripts\python.exe" set "ROLLBACK_FAILED=1"

if "!SERVICE_WAS_RUNNING!"=="1" if "!ROLLBACK_FAILED!"=="0" (
    sc.exe start brandflow-control-plane >nul 2>&1
    if !errorlevel! neq 0 (
        set "ROLLBACK_FAILED=1"
    ) else (
        call :wait_for_service_state RUNNING 30 >nul 2>&1
        if !errorlevel! neq 0 set "ROLLBACK_FAILED=1"
    )
)

if "!SERVICE_EXISTED!"=="0" (
    sc.exe delete brandflow-control-plane >nul 2>&1
    sc.exe query brandflow-control-plane >nul 2>&1
    if !errorlevel! equ 0 set "ROLLBACK_FAILED=1"
)

if "!ROLLBACK_FAILED!"=="1" (
    echo [严重] 自动回滚失败；备份保留在 !BACKUP_VENV!，需要人工恢复 >> "!LOG_FILE!"
    exit /b 1
)
echo [恢复] 已恢复上一虚拟环境和服务状态 >> "!LOG_FILE!"
exit /b 0

:configure_service
reg query "!SERVICE_PARAMS!" >nul 2>&1 || exit /b 1
reg add "!SERVICE_PARAMS!" /v Application /d "%PROJECT_DIR%\.venv\Scripts\python.exe" /f >nul || exit /b 1
reg add "!SERVICE_PARAMS!" /v AppParameters /d "-m apps.control_plane" /f >nul || exit /b 1
reg add "!SERVICE_PARAMS!" /v AppDirectory /d "%PROJECT_DIR%" /f >nul || exit /b 1
reg add "!SERVICE_PARAMS!" /v AppStdout /d "%PROJECT_DIR%\logs\control-plane.log" /f >nul || exit /b 1
reg add "!SERVICE_PARAMS!" /v AppStderr /d "%PROJECT_DIR%\logs\control-plane.log" /f >nul || exit /b 1
reg add "!SERVICE_PARAMS!" /v AppRotateFiles /t REG_DWORD /d 1 /f >nul || exit /b 1
reg add "!SERVICE_PARAMS!" /v AppRotateBytes /t REG_DWORD /d 10485760 /f >nul || exit /b 1
reg add "!SERVICE_PARAMS!" /v AppEnvironmentExtra /t REG_MULTI_SZ /d "DEV_AUTO_TICK=1" /f >nul || exit /b 1
sc.exe config brandflow-control-plane start= auto >nul || exit /b 1
exit /b 0
