@echo off
echo ========================================
echo AI Video Pipeline - Environment Check
echo ========================================
echo.

cd /d "%~dp0"

echo [1] Python Environment
python --version
echo.

echo [2] Checking FFmpeg...
tools\bin\ffmpeg.exe -version 2>nul | findstr "ffmpeg version" && echo [OK] FFmpeg || echo [FAIL] FFmpeg
echo.

echo [3] Checking FFprobe...
tools\bin\ffprobe.exe -version 2>nul | findstr "ffprobe version" && echo [OK] FFprobe || echo [FAIL] FFprobe
echo.

echo [4] Checking Whisper...
tools\bin\whisper-cli.exe --help 2>nul && echo [OK] Whisper || echo [FAIL] Whisper
echo.

echo [5] Checking Whisper Model...
if exist "tools\models\ggml-small.bin" (
    echo [OK] Whisper model found
) else (
    echo [FAIL] Whisper model missing
)
echo.

echo [6] Checking Python Dependencies...
uv run python -c "import fastapi; import pydantic; print('[OK] Dependencies installed')" 2>nul || echo [FAIL] Dependencies
echo.

echo ========================================
echo Environment check complete
echo ========================================
pause
