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

:: 杀掉残留的 Vite dev server（生产环境只应通过后端 17890 访问前端）
echo [0/7] 清理旧进程 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo [%date% %time%] ========== 部署开始 ========== >> "%LOG_FILE%"

:: ============================================
:: Step 1: 前置工具（幂等，缺啥装啥）
:: ============================================
echo [1/7] 检查前置工具 ...

where uv >nul 2>&1 || (
    echo   - 安装 uv ...
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
)

node -v >nul 2>&1 || (
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
:: 确保 node 在 PATH 中（SSH 等非交互 shell 可能不加载）
if not exist "%PROJECT_DIR%\frontend\node_modules" (
    if exist "C:\Program Files\nodejs\node.exe" set "PATH=C:\Program Files\nodejs;%PATH%"
    if exist "%USERPROFILE%\AppData\Local\pnpm\bin\pnpm.CMD" set "PATH=%USERPROFILE%\AppData\Local\pnpm\bin;%PATH%"
    pnpm install --no-frozen-lockfile
    if %errorlevel% neq 0 (
        echo [错误] pnpm install 失败 >> "%LOG_FILE%"
        popd & pause & exit /b 1
    )
) else (
    echo   node_modules 已存在，跳过 install。
)
pnpm build
if %errorlevel% neq 0 (
    echo [错误] pnpm build 失败 >> "%LOG_FILE%"
    popd & pause & exit /b 1
)
popd
echo   前端编译完成。

:: ============================================
:: Step 6: 注册 / 重启计划任务
:: ============================================
echo [6/7] 注册并重启服务 ...
powershell -ExecutionPolicy Bypass -File "%~dp0manage-task.ps1" -Action restart
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
        powershell -ExecutionPolicy Bypass -File "%~dp0manage-task.ps1" -Action restart
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
