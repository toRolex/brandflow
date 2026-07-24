@echo off
chcp 65001 >nul
title Brandflow — 启动服务

echo 正在启动 Brandflow 服务...
nssm start brandflow-control-plane >nul 2>&1
if %errorlevel% equ 0 (
    echo 服务已成功启动！
) else (
    echo 启动失败，请手动检查服务状态。
)
echo Visit: http://localhost:17890
echo.
pause
