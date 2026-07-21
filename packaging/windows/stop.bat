@echo off
chcp 65001 >nul
title Brandflow — 停止后台

echo 正在停止 Brandflow 后台服务...
powershell -ExecutionPolicy Bypass -Command "Stop-ScheduledTask -TaskName brandflow-control-plane" >nul 2>&1
if %errorlevel% equ 0 (
    echo 服务已成功停止。
) else (
    echo 服务未运行或停止失败。
)
echo.
pause
