@echo off
chcp 65001 >nul
title Brandflow — 启动后台

echo 正在启动 Brandflow 后台服务...
powershell -ExecutionPolicy Bypass -Command "Start-ScheduledTask -TaskName brandflow-control-plane" >nul 2>&1
if %errorlevel% equ 0 (
    echo 服务已成功启动！
) else (
    echo 启动失败，请手动检查计划任务状态。
)
echo 访问后台: http://localhost:17890
echo.
pause
