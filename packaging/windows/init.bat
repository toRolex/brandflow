@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — Windows 初始化

set "PROJECT_DIR=%~dp0\..\.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

set "LOG_FILE=%PROJECT_DIR%\logs\init.log"

:: 先创建日志目录，保证后续错误也能写入日志
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

echo [%date% %time%] ========== Brandflow Windows 初始化 ========== >> "%LOG_FILE%"

echo ============================================
echo  Brandflow Windows 初始化
echo  项目目录: %PROJECT_DIR%
echo  日志文件: %LOG_FILE%
echo ============================================
echo.

:: --- 1. 检查 Python / uv ---
echo [1/5] 检查 Python / uv ...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 uv。请先安装 uv: https://docs.astral.sh/uv/ >> "%LOG_FILE%"
    echo [错误] 未找到 uv。请先安装 uv: https://docs.astral.sh/uv/
    echo 日志: %LOG_FILE%
    pause
    exit /b 1
)
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python。请安装 Python 3.11+。 >> "%LOG_FILE%"
    echo [错误] 未找到 Python。请安装 Python 3.11+。
    echo 日志: %LOG_FILE%
    pause
    exit /b 1
)
for /f "tokens=*" %%a in ('python --version') do set PY_VER=%%a
for /f "tokens=*" %%a in ('uv --version') do set UV_VER=%%a
echo   Python: %PY_VER%
echo   uv:     %UV_VER%
echo   Python: %PY_VER%, uv: %UV_VER% >> "%LOG_FILE%"

:: --- 2. 创建部署目录 ---
echo [2/5] 创建部署目录 ...
if not exist "%PROJECT_DIR%\tools\bin" mkdir "%PROJECT_DIR%\tools\bin"
if not exist "%PROJECT_DIR%\config" mkdir "%PROJECT_DIR%\config"
if not exist "%PROJECT_DIR%\workspace" mkdir "%PROJECT_DIR%\workspace"
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"
echo   已确认目录: tools\bin, config, workspace, logs >> "%LOG_FILE%"
echo   目录已创建/确认。

:: --- 3. 运行部署体检 ---
echo [3/5] 运行部署体检 ...
pushd "%PROJECT_DIR%"
uv run python -m packages.deploy_health
set "HEALTH_RC=%errorlevel%"
popd
echo   部署体检退出码: %HEALTH_RC% >> "%LOG_FILE%"
if %HEALTH_RC% equ 0 (
    echo   体检通过。
) else (
    echo   体检发现警告或错误，请查看上方 JSON 输出。
    echo   非致命问题可在补齐外部工具后再次运行 init.bat。
)

:: --- 4. 检查 / 生成 .env ---
echo [4/5] 检查环境变量文件 ...
if not exist "%PROJECT_DIR%\.env" (
    if exist "%PROJECT_DIR%\.env.example" (
        echo   .env 不存在，从 .env.example 复制模板 ...
        copy "%PROJECT_DIR%\.env.example" "%PROJECT_DIR%\.env" >nul
        echo   已生成 %PROJECT_DIR%\.env，请编辑并填入真实 API Key。 >> "%LOG_FILE%"
        echo   已生成 .env 模板，请编辑填入真实 API Key 后再启动服务。
    ) else (
        echo [警告] 未找到 .env.example，请手动创建 %PROJECT_DIR%\.env。 >> "%LOG_FILE%"
        echo [警告] 未找到 .env.example，请手动创建 .env。
    )
) else (
    echo   .env 已存在。
)

:: --- 5. 外部工具提示 ---
echo [5/5] 需要放入 tools\bin\ 的外部工具
echo   以下可执行文件需要随部署包放到 %PROJECT_DIR%\tools\bin\
echo     - ffmpeg.exe
echo     - ffprobe.exe
echo     - whisper-cli.exe
echo.
echo   也可以把它们加入系统 PATH，或通过环境变量覆盖：
echo     FFMPEG_PATH, FFPROBE_PATH, WHISPER_CLI_PATH
echo.
echo   可选工具：
echo     - Git（用于后续代码升级）
echo     - Node.js + npm（用于前端；可运行 setup-prereq.bat 安装）
echo.

echo [%date% %time%] 初始化步骤完成。 >> "%LOG_FILE%"

echo ============================================
echo  初始化完成
echo ============================================
echo 下一步：
echo   1. 将 ffmpeg.exe / ffprobe.exe / whisper-cli.exe 复制到 tools\bin\
echo   2. 编辑 .env 填入真实 API Key
echo   3. 在前端目录执行 npm install 安装依赖
echo   4. 运行 packaging\windows\start.bat
if %HEALTH_RC% neq 0 (
echo   5. 根据体检输出修复依赖/端口问题
)
echo.
pause
