@echo off
echo ========================================
echo AI Video Pipeline - Control Plane
echo ========================================
echo.
echo Starting FastAPI server on port 17890...
echo Web UI: http://127.0.0.1:17890
echo.
echo Press Ctrl+C to stop
echo ========================================
echo.

cd /d "%~dp0"
uv run python -m apps.control_plane
