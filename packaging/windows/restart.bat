@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 重启服务

set "PROJECT_DIR=%~dp0..\.."
set "LOG_FILE=%PROJECT_DIR%\logs\control-plane.log"

echo 正在重启 Brandflow ...

:: 优先使用系统 nssm；找不到则回退到项目 tools 目录
set "NSSM_CMD=nssm"
where nssm >nul 2>&1 || (
    if exist "%PROJECT_DIR%\tools\nssm-2.24\win64\nssm.exe" (
        set "NSSM_CMD=%PROJECT_DIR%\tools\nssm-2.24\win64\nssm.exe"
    ) else (
        echo [错误] 未找到 nssm，无法重启服务。
        echo 请先运行 deploy.bat 完成初始化。
        pause
        exit /b 1
    )
)

echo 停止服务 ...
"!NSSM_CMD!" stop brandflow-control-plane >nul 2>&1
timeout /t 2 /nobreak >nul

echo 启动服务 ...
"!NSSM_CMD!" start brandflow-control-plane >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 服务启动失败，请检查日志: %LOG_FILE%
    pause
    exit /b 1
)

echo 等待健康检查 ...
timeout /t 5 /nobreak >nul

curl --noproxy "*" -f http://127.0.0.1:17890/api/health >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 健康检查未通过，服务可能仍在启动中。
    echo 请稍后访问 http://127.0.0.1:17890 或查看日志: %LOG_FILE%
) else (
    echo 重启成功，访问 http://127.0.0.1:17890
    timeout /t 2 /nobreak >nul
    start http://127.0.0.1:17890
)

echo.
pause
