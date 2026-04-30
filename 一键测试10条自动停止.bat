@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Ziyuantang Pipeline Test 10

set "PYTHONUTF8=1"
set "PIPELINE_DRY_RUN=0"
if not defined FFMPEG_PATH set "FFMPEG_PATH=%CD%\tools\bin\ffmpeg.exe"
if not defined FFPROBE_PATH set "FFPROBE_PATH=%CD%\tools\bin\ffprobe.exe"
if not defined WHISPER_PATH set "WHISPER_PATH=%CD%\tools\bin\whisper-cli.exe"
if not defined MODEL_PATH set "MODEL_PATH=%CD%\tools\models\ggml-small.bin"
if not defined COVER_FONT_PATH set "COVER_FONT_PATH=C:\Windows\Fonts\simhei.ttf"
if not defined SUBTITLE_MODE set "SUBTITLE_MODE=script_timed"
set "BATCH_DIRECTION_FILE=%CD%\.runtime_batch_direction.txt"

set "PYTHON_CMD=py -3.11"
py -3.11 --version >nul 2>nul
if errorlevel 1 set "PYTHON_CMD=python"

if not exist ".\手动音频池" mkdir ".\手动音频池"
if not exist ".\手动音频池\_已使用" mkdir ".\手动音频池\_已使用"

echo ================================================================
echo Test 10 videos, auto stop when 10 completed or 30 minutes timeout
echo ================================================================
echo Materials: 001ProjectName + Chinese raw-material folder + mp4 files
echo Existing audio: manual audio pool per project, or manual audio pool root
echo Checkpoint audio: 001ProjectName task folder audio file named job_id_mp3
echo Project folder names must start from 001 to 999, for example 001yangdujun.
echo.
echo Dashboard browser auto-open is disabled.
echo Dashboard URL if needed: http://127.0.0.1:17890/
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "tools\launcher_check.ps1" -Mode Media
if errorlevel 1 (
    echo [ERROR] Media tool preflight failed.
    pause
    exit /b 1
)

%PYTHON_CMD% main_controller.py --root . --non-interactive --check-media
if errorlevel 1 (
    echo [ERROR] Python media preflight failed.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "tools\launcher_check.ps1" -Mode Materials
if errorlevel 1 (
    echo [ERROR] No runnable 001xxx project was found.
    echo Rename the project folder to something like 001yangdujun, then put mp4 files in its raw-material folder.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "tools\input_batch_direction.ps1" -OutputPath "%BATCH_DIRECTION_FILE%"
if errorlevel 1 (
    echo [WARN] Batch direction popup failed. Continuing with blank direction.
)

%PYTHON_CMD% main_controller.py --root . --host 127.0.0.1 --port 17890 --batch-size 10 --non-interactive --recover-existing-assets --stop-after-completed 10 --max-runtime-seconds 1800

echo.
echo Test controller exited. Running acceptance report...
%PYTHON_CMD% tools\validate_delivery.py --root . --expected 10
echo.
pause
