@echo off
cd /d "%~dp0..\.."
uv run --project . python -m apps.runtime_worker
