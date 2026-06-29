@echo off
chcp 65001 >nul
title 滋元堂 — NSSM 服务注册
setlocal enabledelayedexpansion

:: 获取脚本所在目录的上两级 = 项目根目录
set PROJECT_DIR=%~dp0..\..
pushd "%PROJECT_DIR%"
set PROJECT_DIR=%CD%
popd

echo ============================================
echo  滋元堂矩阵流水线 — NSSM 服务注册
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
echo [1/2] 注册控制面板务（ziyuantang-control-plane）...
nssm stop ziyuantang-control-plane >nul 2>&1
nssm remove ziyuantang-control-plane confirm >nul 2>&1
nssm install ziyuantang-control-plane "uv" "run python -m apps.control_plane"
nssm set ziyuantang-control-plane AppDirectory "%PROJECT_DIR%"
nssm set ziyuantang-control-plane AppStdout "%PROJECT_DIR%\logs\control-plane.log"
nssm set ziyuantang-control-plane AppStderr "%PROJECT_DIR%\logs\control-plane.log"
nssm set ziyuantang-control-plane AppRotateFiles 1
nssm set ziyuantang-control-plane AppRotateSeconds 86400
nssm set ziyuantang-control-plane Start SERVICE_AUTO_START
echo   已注册。

:: Worker 服务
echo [2/2] 注册 Worker 服务（ziyuantang-worker）...
nssm stop ziyuantang-worker >nul 2>&1
nssm remove ziyuantang-worker confirm >nul 2>&1
nssm install ziyuantang-worker "uv" "run python -m apps.runtime_worker"
nssm set ziyuantang-worker AppDirectory "%PROJECT_DIR%"
nssm set ziyuantang-worker AppStdout "%PROJECT_DIR%\logs\worker.log"
nssm set ziyuantang-worker AppStderr "%PROJECT_DIR%\logs\worker.log"
nssm set ziyuantang-worker AppRotateFiles 1
nssm set ziyuantang-worker AppRotateSeconds 86400
nssm set ziyuantang-worker AppExit Default Exit
nssm set ziyuantang-worker Start SERVICE_AUTO_START
echo   已注册。

echo.
echo ============================================
echo  服务注册完成！可以运行以下命令管理：
echo.
echo  net start ziyuantang-control-plane
echo  net start ziyuantang-worker
echo  nssm status ziyuantang-control-plane
echo  nssm status ziyuantang-worker
echo ============================================
pause
