@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 查看状态

set NSSM=nssm.exe
where nssm >nul 2>&1 || (
    if exist "%~dp0..\..\tools\nssm-2.24\win64\nssm.exe" set "NSSM=%~dp0..\..\tools\nssm-2.24\win64\nssm.exe"
    if exist "C:\Program Files\NSSM\nssm.exe" set "NSSM=C:\Program Files\NSSM\nssm.exe"
)

echo Brandflow 后台服务状态：
%NSSM% status brandflow-control-plane
echo.
echo 按任意键查看 Python 进程...
pause >nul
tasklist /FI "IMAGENAME eq python.exe" /V /FO LIST 2>nul
if %errorlevel% neq 0 (
    echo (无正在运行的 Python 进程)
)
echo.
pause
