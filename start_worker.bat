@echo off
echo ========================================
echo AI Video Pipeline - Worker
echo ========================================
echo.
echo Starting worker (connecting to control plane)...
echo.
echo Press Ctrl+C to stop
echo ========================================
echo.

cd /d "%~dp0"
uv run python -m apps.runtime_worker
