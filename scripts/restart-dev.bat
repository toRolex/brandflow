@echo off
chcp 65001 >nul
title Brandflow - Restart Dev Environment

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%restart-dev.ps1"

where pwsh >nul 2>&1
if %errorlevel% equ 0 (
    pwsh -NoProfile -File "%PS_SCRIPT%" %*
    goto :end
)

where powershell >nul 2>&1
if %errorlevel% equ 0 (
    powershell -NoProfile -File "%PS_SCRIPT%" %*
    goto :end
)

echo Error: PowerShell not found. Please install PowerShell 7 or later.
echo Download: https://aka.ms/powershell
pause
exit /b 1

:end
if %errorlevel% neq 0 (
    echo.
    echo Startup failed, exit code: %errorlevel%
    pause
)
