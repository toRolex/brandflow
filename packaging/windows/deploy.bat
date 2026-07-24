@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 一键部署

set "PROJECT_DIR=D:\brandflow"

:: 自动提权（安装工具和注册服务需要管理员权限）
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 请求管理员权限...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

if not exist "%PROJECT_DIR%" (
    echo [错误] 项目目录 %PROJECT_DIR% 不存在
    pause
    exit /b 1
)

set "LOG_FILE=%PROJECT_DIR%\logs\deploy.log"
if not exist "%PROJECT_DIR%\logs\" mkdir "%PROJECT_DIR%\logs\"

echo ============================================
echo  Brandflow 一键部署
echo ============================================
echo  项目: %PROJECT_DIR%
echo  日志: %LOG_FILE%
echo ============================================
echo.

echo [%date% %time%] ========== 部署开始 ========== >> "%LOG_FILE%"

:: ============================================
:: Step 1: 前置工具（幂等，缺啥装啥）
:: ============================================
echo [1/7] 检查前置工具 ...

where uv >nul 2>&1 || (
    echo   - 安装 uv ...
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
)

where node >nul 2>&1 || (
    if exist "C:\Program Files\nodejs\node.exe" (
        set "PATH=C:\Program Files\nodejs;%PATH%"
    ) else (
        echo   - 安装 Node.js 20 ...
        curl.exe -sL https://nodejs.org/dist/v20.18.3/node-v20.18.3-x64.msi -o %TEMP%\node-installer.msi
        msiexec /i %TEMP%\node-installer.msi /qn /norestart
        if exist "C:\Program Files\nodejs\node.exe" set "PATH=C:\Program Files\nodejs;%PATH%"
    )
)

where pnpm >nul 2>&1 || (
    if exist "%USERPROFILE%\AppData\Local\pnpm\bin\pnpm.CMD" (
        set "PATH=%USERPROFILE%\AppData\Local\pnpm\bin;%PATH%"
    ) else (
        echo   - 安装 pnpm ...
        powershell -c "iwr https://get.pnpm.io/install.ps1 -useb | iex"
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
if not exist "%PROJECT_DIR%\workspace" mkdir "%PROJECT_DIR%\workspace"

if not exist "%PROJECT_DIR%\.env" (
    if exist "%PROJECT_DIR%\.env.example" (
        echo   .env 不存在，从 .env.example 复制 ...
        copy "%PROJECT_DIR%\.env.example" "%PROJECT_DIR%\.env" >nul
        echo   已生成 .env 模板，请编辑填入 API Key 后再启动。
    )
)
echo   目录已确认。

:: ============================================
:: Step 3: 拉取最新代码
:: ============================================
echo [3/7] 拉取最新代码 ...
pushd "%PROJECT_DIR%"
git fetch --tags
git pull --rebase
if %errorlevel% neq 0 (
    echo [错误] git pull 失败 >> "%LOG_FILE%"
    pause
    exit /b %errorlevel%
)
popd

:: ============================================
:: Step 4: Python 依赖
:: ============================================
echo [4/7] 安装 Python 依赖 ...
pushd "%PROJECT_DIR%"
uv sync --all-extras --dev
if %errorlevel% neq 0 (
    echo [错误] uv sync 失败 >> "%LOG_FILE%"
    pause
    exit /b %errorlevel%
)
popd

:: ============================================
:: Step 5: 前端编译
:: ============================================
echo [5/7] 编译前端 ...
pushd "%PROJECT_DIR%\frontend"
if exist "C:\Program Files\nodejs\node.exe" set "PATH=C:\Program Files\nodejs;%PATH%"
if exist "%USERPROFILE%\AppData\Local\pnpm\bin\pnpm.CMD" set "PATH=%USERPROFILE%\AppData\Local\pnpm\bin;%PATH%"

if not exist "node_modules" (
    call pnpm install --no-frozen-lockfile
    if %errorlevel% neq 0 (
        echo [错误] pnpm install 失败 >> "%LOG_FILE%"
        popd
        pause
        exit /b %errorlevel%
    )
)
call pnpm build
if %errorlevel% neq 0 (
    echo [错误] pnpm build 失败 >> "%LOG_FILE%"
    popd
    pause
    exit /b %errorlevel%
)
popd
echo   前端编译完成。

:: ============================================
:: Step 6: 注册 / 启动服务
:: ============================================
echo [6/7] 注册并启动服务 ...
nssm restart brandflow-control-plane >nul 2>&1 || (
    nssm install brandflow-control-plane cmd /c "uv run --directory %PROJECT_DIR% python -m apps.control_plane"
    nssm set brandflow-control-plane AppDirectory "%PROJECT_DIR%"
    nssm set brandflow-control-plane AppStdout "%PROJECT_DIR%\logs\control-plane.log"
    nssm set brandflow-control-plane AppStderr "%PROJECT_DIR%\logs\control-plane.log"
    nssm set brandflow-control-plane AppRotateFiles 1
    nssm set brandflow-control-plane AppRotateBytes 10485760
    nssm set brandflow-control-plane Start SERVICE_AUTO_START
    nssm start brandflow-control-plane
)
echo   服务已启动。

:: ============================================
:: Step 7: 健康检查
:: ============================================
echo [7/7] 健康检查 ...
timeout /t 5 /nobreak >nul

curl --noproxy "*" -f http://127.0.0.1:17890/api/health >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 健康检查失败，请检查日志: %LOG_FILE%
    pause
    exit /b 1
)

echo [%date% %time%] ========== 部署成功 ========== >> "%LOG_FILE%"
echo.
echo ============================================
echo  部署成功
echo  访问: http://127.0.0.1:17890
echo  日志: %LOG_FILE%
echo ============================================
pause
