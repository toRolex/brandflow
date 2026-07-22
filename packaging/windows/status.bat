@echo off
chcp 65001 >nul
title Brandflow — 查看状态

echo Brandflow 后台服务状态：
powershell -ExecutionPolicy Bypass -Command "Get-ScheduledTask -TaskName brandflow-control-plane | Format-List TaskName,State"
echo.
echo Python 进程：
tasklist /FI "IMAGENAME eq python.exe" /V /FO LIST 2>nul
if %errorlevel% neq 0 (
    echo (无正在运行的 Python 进程)
)
echo.
pause
