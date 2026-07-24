@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 快速更新

set "PROJECT_DIR=%~dp0..\.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

set "LOG_FILE=%~dp0update.log"

echo ============================================
echo  Brandflow 快速更新
echo  1. 拉取最新代码
echo  2. 更新 Python 依赖
echo  3. 编译前端
echo  4. 构建完成，后端将在下次 nssm 重启后加载新代码
echo ============================================

:: --- 1. 拉取最新代码 ---
echo [1/4] 拉取最新代码 ...
git pull
if %errorlevel% neq 0 (
    echo [错误] git pull 失败，请检查网络或冲突
    exit /b %errorlevel%
)

:: --- 2. 更新 Python 依赖 ---
echo [2/4] 更新 Python 依赖 ...
uv sync --all-extras --dev
if %errorlevel% neq 0 (
    echo [错误] uv sync 失败
    exit /b %errorlevel%
)

:: --- 3. 编译前端 ---
echo [3/4] 编译前端 ...
pushd "%PROJECT_DIR%\frontend"
call pnpm install --no-frozen-lockfile
if %errorlevel% neq 0 (
    echo [错误] pnpm install 失败
    popd
    exit /b %errorlevel%
)
call pnpm build
if %errorlevel% neq 0 (
    echo [错误] pnpm build 失败
    popd
    exit /b %errorlevel%
)
popd

:: --- 4. 重启 Worker（控制面不重启，新代码在下次 nssm 重启后加载） ---
echo [4/4] 重启 Worker ...
set "NSSM=%~dp0..\..\tools\nssm-2.24\win64\nssm.exe"
if exist "%NSSM%" (
    "%NSSM%" restart brandflow-worker
    if %errorlevel% neq 0 (
        echo [警告] brandflow-worker 重启失败，可能未注册
    )
) else (
    echo [警告] nssm 未找到，跳过 Worker 重启
)

echo.
echo ============================================
echo  更新完成！
echo  后端: http://127.0.0.1:17890
echo ============================================
