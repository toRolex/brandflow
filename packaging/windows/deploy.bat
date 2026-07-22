@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 一键部署

set "PROJECT_DIR=%~dp0..\.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

set "LOG_FILE=%PROJECT_DIR%\logs\deploy.log"
if not exist "%PROJECT_DIR%\logs\" mkdir "%PROJECT_DIR%\logs\"

echo ============================================
echo  Brandflow 一键部署
echo  1. 自动安装前置工具（首次）
echo  2. 拉取最新代码
echo  3. 安装依赖 + 编译前端
echo  4. 注册 / 重启服务
echo  5. 健康检查 + 自动回滚
echo ============================================
echo  项目: %PROJECT_DIR%
echo  日志: %LOG_FILE%
echo ============================================
echo.

:: ============================================
:: Step 0: 自动提权（装工具、操作服务需要管理员）
:: ============================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [0/7] 请求管理员权限...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

echo [%date% %time%] ========== 部署开始 ========== >> "%LOG_FILE%"

:: ============================================
:: Step 1: 前置工具（幂等，缺啥装啥）
:: ============================================
echo [1/7] 检查前置工具 ...

where uv >nul 2>&1 || (
    echo   - 安装 uv ...
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
)

where nvm >nul 2>&1 || (
    echo   - 安装 nvm-windows ...
    powershell -c "Invoke-WebRequest -Uri https://github.com/coreybutler/nvm-windows/releases/download/1.2.2/nvm-setup.exe -OutFile %TEMP%\nvm-setup.exe; Start-Process %TEMP%\nvm-setup.exe -ArgumentList '/S' -Wait"
)

node -v >nul 2>&1 || (
    echo   - 安装 Node.js 20 ...
    call nvm install 20.18.3
    call nvm use 20.18.3
)

where pnpm >nul 2>&1 || (
    echo   - 安装 pnpm ...
    powershell -c "iwr https://get.pnpm.io/install.ps1 -useb | iex"
)

where ffmpeg >nul 2>&1 || (
    echo   - 安装 FFmpeg ...
    winget install --id Gyan.FFmpeg -e --silent --accept-package-agreements
)

where nssm >nul 2>&1 || (
    echo   - 安装 NSSM ...
    winget install --id NSSM.NSSM -e --silent --accept-package-agreements
)

echo   工具就绪。

:: ============================================
:: Step 2: 初始化目录 + .env
:: ============================================
echo [2/7] 初始化项目目录 ...
if not exist "%PROJECT_DIR%\tools\bin" mkdir "%PROJECT_DIR%\tools\bin"
if not exist "%PROJECT_DIR%\config" mkdir "%PROJECT_DIR%\config"
if not exist "%PROJECT_DIR%\workspace" mkdir "%PROJECT_DIR%\workspace"
echo   目录已确认。

if not exist "%PROJECT_DIR%\.env" (
    if exist "%PROJECT_DIR%\.env.example" (
        echo   .env 不存在，从 .env.example 复制 ...
        copy "%PROJECT_DIR%\.env.example" "%PROJECT_DIR%\.env" >nul
        echo   ⚠ 已生成 .env 模板，请编辑填入 API Key 后再启动。
    ) else (
        echo   ⚠ .env 和 .env.example 都不存在，请手动创建 .env。
    )
)

:: ============================================
:: Step 3: 拉取最新代码
:: ============================================
echo [3/7] 拉取最新代码 ...
git fetch --tags
git tag -a "deploy-%date:~0,4%%date:~5,2%%date:~8,2%-%time:~0,2%%time:~3,2%%time:~6,2%" -m "deploy before update" >nul 2>&1
git pull
if %errorlevel% neq 0 (
    echo [错误] git pull 失败，请检查网络或冲突 >> "%LOG_FILE%"
    pause
    exit /b 1
)

:: ============================================
:: Step 4: Python 依赖
:: ============================================
echo [4/7] 安装 Python 依赖 ...
uv sync --all-extras --dev
if %errorlevel% neq 0 (
    echo [错误] uv sync 失败 >> "%LOG_FILE%"
    pause
    exit /b 1
)

:: ============================================
:: Step 5: 前端编译
:: ============================================
echo [5/7] 编译前端 ...
pushd "%PROJECT_DIR%\frontend"
call nvm use 20.18.3 2>nul
pnpm install --no-frozen-lockfile
if %errorlevel% neq 0 (
    echo [错误] pnpm install 失败 >> "%LOG_FILE%"
    popd & pause & exit /b 1
)
pnpm build
if %errorlevel% neq 0 (
    echo [错误] pnpm build 失败 >> "%LOG_FILE%"
    popd & pause & exit /b 1
)
popd
echo   前端编译完成。

:: ============================================
:: Step 6: 注册 / 重启 Windows 服务
:: ============================================
echo [6/7] 注册并重启服务 ...

nssm status brandflow-control-plane >nul 2>&1
if errorlevel 2 (
    echo   - 注册控制面服务 ...
    nssm install brandflow-control-plane "uv" "run --project . python -m apps.control_plane"
    nssm set brandflow-control-plane AppDirectory "%PROJECT_DIR%"
    nssm set brandflow-control-plane AppStdout "%PROJECT_DIR%\logs\control-plane.log"
    nssm set brandflow-control-plane AppStderr "%PROJECT_DIR%\logs\control-plane.log"
    nssm set brandflow-control-plane AppRotateFiles 1
    nssm set brandflow-control-plane AppRotateSeconds 86400
    nssm set brandflow-control-plane Start SERVICE_AUTO_START
)

nssm status brandflow-worker >nul 2>&1
if errorlevel 2 (
    echo   - 注册 Worker 服务 ...
    nssm install brandflow-worker "uv" "run --project . python -m apps.runtime_worker"
    nssm set brandflow-worker AppDirectory "%PROJECT_DIR%"
    nssm set brandflow-worker AppStdout "%PROJECT_DIR%\logs\worker.log"
    nssm set brandflow-worker AppStderr "%PROJECT_DIR%\logs\worker.log"
    nssm set brandflow-worker AppRotateFiles 1
    nssm set brandflow-worker AppRotateSeconds 86400
    nssm set brandflow-worker AppExit Default Exit
    nssm set brandflow-worker Start SERVICE_AUTO_START
)

:: 确保服务参数是最新的（覆盖旧版部署）
nssm set brandflow-control-plane AppParameters "run --project . python -m apps.control_plane" >nul 2>&1
nssm set brandflow-worker AppParameters "run --project . python -m apps.runtime_worker" >nul 2>&1

nssm restart brandflow-control-plane
if errorlevel 1 nssm start brandflow-control-plane

nssm restart brandflow-worker
if errorlevel 1 nssm start brandflow-worker

echo   服务已启动。

:: ============================================
:: Step 7: 健康检查 + 自动回滚
:: ============================================
echo [7/7] 健康检查 ...
timeout /t 5 /nobreak >nul

curl -f http://127.0.0.1:17890/api/health >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 健康检查失败，触发自动回滚 ... >> "%LOG_FILE%"
    for /f "delims=" %%t in ('git tag --sort=-creatordate ^| findstr "deploy-" ^| more +1') do (
        set "ROLLBACK_TAG=%%t"
        goto :rollback
    )
    :rollback
    if defined ROLLBACK_TAG (
        echo   回滚到 !ROLLBACK_TAG! ...
        git reset --hard !ROLLBACK_TAG!
        nssm restart brandflow-control-plane
        nssm restart brandflow-worker
        echo [完成] 已回滚 !ROLLBACK_TAG! >> "%LOG_FILE%"
        echo   已回滚到 !ROLLBACK_TAG!，请检查服务状态。
    ) else (
        echo [错误] 找不到可回滚的 tag，请手动处理 >> "%LOG_FILE%"
    )
    pause
    exit /b 1
)

:: 清理旧 tag（保留最近 10 个）
for /f "skip=10 delims=" %%t in ('git tag --sort=-creatordate ^| findstr "deploy-"') do (
    git tag -d %%t >nul
)

echo [%date% %time%] ========== 部署成功 ========== >> "%LOG_FILE%"
echo.
echo ============================================
echo  部署成功！
echo  后端: http://127.0.0.1:17890/api/health
echo  日志: %LOG_FILE%
echo ============================================
pause
