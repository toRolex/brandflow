@echo off
chcp 65001 >nul
title Brandflow — NSSM 服务注册
setlocal enabledelayedexpansion

:: 获取脚本所在目录的上两级 = 项目根目录
set PROJECT_DIR=%~dp0..\..
pushd "%PROJECT_DIR%"
set PROJECT_DIR=%CD%
popd

echo ============================================
echo  Brandflow 短视频自动化系统 — NSSM 服务注册
echo ============================================
echo 项目路径: %PROJECT_DIR%
echo.
echo 此脚本需要管理员权限。
echo.

:: 检查 NSSM
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 NSSM，请先运行 setup-prereq.bat
    pause
    exit /b 1
)

:: 控制面板务
echo [1/2] 注册控制面板务（brandflow-control-plane）...
nssm stop brandflow-control-plane >nul 2>&1
nssm remove brandflow-control-plane confirm >nul 2>&1
nssm install brandflow-control-plane "uv" "run python -m apps.control_plane"
nssm set brandflow-control-plane AppDirectory "%PROJECT_DIR%"
nssm set brandflow-control-plane AppStdout "%PROJECT_DIR%\logs\control-plane.log"
nssm set brandflow-control-plane AppStderr "%PROJECT_DIR%\logs\control-plane.log"
nssm set brandflow-control-plane AppRotateFiles 1
nssm set brandflow-control-plane AppRotateSeconds 86400
nssm set brandflow-control-plane Start SERVICE_AUTO_START
echo   已注册。

:: Worker 服务
echo [2/2] 注册 Worker 服务（brandflow-worker）...
nssm stop brandflow-worker >nul 2>&1
nssm remove brandflow-worker confirm >nul 2>&1
nssm install brandflow-worker "uv" "run python -m apps.runtime_worker"
nssm set brandflow-worker AppDirectory "%PROJECT_DIR%"
nssm set brandflow-worker AppStdout "%PROJECT_DIR%\logs\worker.log"
nssm set brandflow-worker AppStderr "%PROJECT_DIR%\logs\worker.log"
nssm set brandflow-worker AppRotateFiles 1
nssm set brandflow-worker AppRotateSeconds 86400
nssm set brandflow-worker AppExit Default Exit
nssm set brandflow-worker Start SERVICE_AUTO_START
echo   已注册。

echo.
echo ============================================
echo  服务注册完成！可以运行以下命令管理：
echo.
echo  net start brandflow-control-plane
echo  net start brandflow-worker
echo  nssm status brandflow-control-plane
echo  nssm status brandflow-worker
echo ============================================
pause
