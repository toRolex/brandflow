@echo off
chcp 65001 >nul
title Brandflow — 启动服务

echo 正在启动 Brandflow ...
nssm start brandflow-control-plane
if %errorlevel% equ 0 (
    echo 服务已启动。
    timeout /t 2 /nobreak >nul
    start http://127.0.0.1:17890
) else (
    echo 启动失败，请运行 deploy.bat 初始化服务。
)
echo.
pause
