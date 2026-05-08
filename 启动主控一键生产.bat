@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Ziyuantang Pipeline

set "PYTHONUTF8=1"
set "PIPELINE_DRY_RUN=0"
set "DASHBOARD_URL=http://127.0.0.1:17890/"
if not defined FFMPEG_PATH set "FFMPEG_PATH=%CD%\tools\bin\ffmpeg.exe"
if not defined FFPROBE_PATH set "FFPROBE_PATH=%CD%\tools\bin\ffprobe.exe"
if not defined WHISPER_PATH set "WHISPER_PATH=%CD%\tools\bin\whisper-cli.exe"
if not defined MODEL_PATH set "MODEL_PATH=%CD%\tools\models\ggml-small.bin"
if not defined COVER_FONT_PATH set "COVER_FONT_PATH=C:\Windows\Fonts\simhei.ttf"
if not defined SUBTITLE_MODE set "SUBTITLE_MODE=script_timed"
set "BATCH_DIRECTION_FILE=%CD%\.runtime_batch_direction.txt"

echo ================================================================
echo Ziyuantang Pipeline - One Click Launcher
echo ================================================================
echo.

echo [1/6] Checking uv...
uv --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] uv was not found. Install uv first: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

echo [2/6] Syncing Python dependencies with uv...
uv sync --project "%CD%" --locked
if errorlevel 1 (
    echo [ERROR] uv sync failed. Check pyproject.toml or uv.lock.
    pause
    exit /b 1
)

echo [3/6] Checking .env...
if not exist ".env" (
    echo [ERROR] Missing .env file in root directory.
    echo Required keys: DEEPSEEK_API_KEY, MIMO_API_KEY
    echo Copy .env.example to .env and fill keys locally. Do not send the file out.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "tools\launcher_check.ps1" -Mode Env
if errorlevel 1 (
    echo [ERROR] .env is missing one or more required keys.
    pause
    exit /b 1
)

echo [4/6] Checking engine files...
echo Engine paths locked:
echo   ffmpeg  = %FFMPEG_PATH%
echo   ffprobe = %FFPROBE_PATH%
echo   whisper = %WHISPER_PATH%
echo   model   = %MODEL_PATH%
echo   font    = %COVER_FONT_PATH%
echo   subtitles = %SUBTITLE_MODE%
if not exist "%FFMPEG_PATH%" (
    echo [ERROR] Missing ffmpeg engine.
    echo Expected: %FFMPEG_PATH%
    echo Run: powershell -ExecutionPolicy Bypass -File tools\prepare_local_tools.ps1
    pause
    exit /b 1
)
if not exist "%FFPROBE_PATH%" (
    echo [ERROR] Missing ffprobe engine.
    echo Expected: %FFPROBE_PATH%
    echo Run: powershell -ExecutionPolicy Bypass -File tools\prepare_local_tools.ps1
    pause
    exit /b 1
)
if /I "%SUBTITLE_MODE%"=="whisper" (
    if not exist "%WHISPER_PATH%" (
        echo [ERROR] Missing whisper engine.
        echo Expected: %WHISPER_PATH%
        echo Run: powershell -ExecutionPolicy Bypass -File tools\prepare_local_tools.ps1
        pause
        exit /b 1
    )
    if not exist "%MODEL_PATH%" (
        echo [ERROR] Missing whisper model.
        echo Expected: %MODEL_PATH%
        echo Run: powershell -ExecutionPolicy Bypass -File tools\prepare_local_tools.ps1
        pause
        exit /b 1
    )
)
if not exist "%COVER_FONT_PATH%" (
    echo [ERROR] Missing cover font.
    echo Expected: %COVER_FONT_PATH%
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\launcher_check.ps1" -Mode Media
if errorlevel 1 (
    echo [ERROR] Media tool preflight failed.
    pause
    exit /b 1
)
uv run --project "%CD%" main_controller.py --root . --non-interactive --check-media
if errorlevel 1 (
    echo [ERROR] Python media preflight failed.
    pause
    exit /b 1
)
echo Manual audio pool is ready.
echo   Materials folder: 001ProjectName + Chinese raw-material folder.
echo   Existing mp3 option A: manual audio pool + 001ProjectName + mp3 files.
echo   Existing mp3 option B: manual audio pool root + mp3 files.
echo   Existing mp3 option C: task folder audio file named job_id_mp3.
echo   Startup scans existing audio/base/srt/final files and resumes from checkpoints.

echo [5/6] Checking project materials...
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\launcher_check.ps1" -Mode Materials
if errorlevel 1 (
    echo [ERROR] No runnable 001xxx project was found.
    echo Prepare at least one project like this:
    echo   001ProjectName\
    echo     Chinese raw-material folder with mp4 files
    echo     optional cover image
    echo Project folder names must start from 001 to 999, for example 001yangdujun.
    pause
    exit /b 1
)

echo [6/6] Batch direction and starting controller...
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\input_batch_direction.ps1" -OutputPath "%BATCH_DIRECTION_FILE%"
if errorlevel 1 (
    echo [WARN] Batch direction popup failed. Continuing with blank direction.
)
echo Dashboard browser auto-open is disabled.
echo Dashboard URL if needed: %DASHBOARD_URL%
echo.

uv run --project "%CD%" main_controller.py --root . --host 127.0.0.1 --port 17890 --batch-size 10 --non-interactive --recover-existing-assets

echo.
echo Controller exited.
pause
