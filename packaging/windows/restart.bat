@echo off
chcp 65001 >nul
title Brandflow — 重启后台

echo 正在重启 Brandflow 后台服务...
powershell -ExecutionPolicy Bypass -Command "Stop-ScheduledTask -TaskName brandflow-control-plane; Start-ScheduledTask -TaskName brandflow-control-plane" >nul 2>&1
if %errorlevel% equ 0 (
    echo 服务已成功重启！
) else (
    echo 重启失败，请手动检查。
)
echo 访问后台: http://localhost:17890
echo.
pause
