@echo off
chcp 65001 >nul
title Brandflow — 停止服务

echo 正在停止后端服务 ...
nssm stop brandflow-control-plane
if %errorlevel% equ 0 (
    echo 后端服务已停止。
) else (
    echo 后端服务未运行或停止失败。
)
echo.
pause
