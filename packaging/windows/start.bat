@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 启动服务

:: 自动查找 nssm（优先 PATH，再查常见路径）
set NSSM=nssm.exe
where nssm >nul 2>&1 || (
    if exist "%~dp0..\..\tools\nssm-2.24\win64\nssm.exe" set "NSSM=%~dp0..\..\tools\nssm-2.24\win64\nssm.exe"
    if exist "C:\Program Files\NSSM\nssm.exe" set "NSSM=C:\Program Files\NSSM\nssm.exe"
)

echo 正在启动 Brandflow 后台服务...
%NSSM% start brandflow-control-plane >nul 2>&1
if %errorlevel% equ 0 (
    echo 服务已成功启动！
) else (
    echo 服务可能已在运行。
)
echo 访问后台: http://localhost:17890
echo.
pause
