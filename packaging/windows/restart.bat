@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 重启服务

set NSSM=nssm.exe
where nssm >nul 2>&1 || (
    if exist "%~dp0..\..\tools\nssm-2.24\win64\nssm.exe" set "NSSM=%~dp0..\..\tools\nssm-2.24\win64\nssm.exe"
    if exist "C:\Program Files\NSSM\nssm.exe" set "NSSM=C:\Program Files\NSSM\nssm.exe"
)

echo 正在重启 Brandflow 后台服务...
%NSSM% restart brandflow-control-plane
if %errorlevel% equ 0 (
    echo 服务已成功重启！
) else (
    echo 重启失败，尝试启动...
    %NSSM% start brandflow-control-plane >nul 2>&1
)
echo 访问后台: http://localhost:17890
echo.
pause
