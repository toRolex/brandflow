@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 快速更新

set "PROJECT_DIR=%~dp0..\.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

set "LOG_FILE=%~dp0update.log"

echo ============================================ >> "%LOG_FILE%" 2>&1
echo  Brandflow 快速更新 >> "%LOG_FILE%" 2>&1
echo  1. 拉取最新代码 >> "%LOG_FILE%" 2>&1
echo  2. 更新 Python 依赖 >> "%LOG_FILE%" 2>&1
echo  3. 编译前端 >> "%LOG_FILE%" 2>&1
echo  4. 重启后端服务 + Worker >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1

:: --- 1. 拉取最新代码 ---
echo [1/4] 拉取最新代码 ... >> "%LOG_FILE%" 2>&1
git pull >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [错误] git pull 失败，请检查网络或冲突 >> "%LOG_FILE%" 2>&1
    exit /b %errorlevel%
)

:: --- 2. 更新 Python 依赖 ---
echo [2/4] 更新 Python 依赖 ... >> "%LOG_FILE%" 2>&1
uv sync --all-extras --dev >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [错误] uv sync 失败 >> "%LOG_FILE%" 2>&1
    exit /b %errorlevel%
)

:: --- 3. 编译前端 ---
echo [3/4] 编译前端 ... >> "%LOG_FILE%" 2>&1
pushd "%PROJECT_DIR%\frontend"
call pnpm install --no-frozen-lockfile >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [错误] pnpm install 失败 >> "%LOG_FILE%" 2>&1
    popd
    exit /b %errorlevel%
)
call pnpm build >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [错误] pnpm build 失败 >> "%LOG_FILE%" 2>&1
    popd
    exit /b %errorlevel%
)
popd

:: --- 4. 重启服务（先 Worker 后 Control-Plane，减少排队任务丢失） ---
echo [4/4] 重启服务 ... >> "%LOG_FILE%" 2>&1
nssm restart brandflow-worker >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [警告] brandflow-worker 重启失败，可能未注册 >> "%LOG_FILE%" 2>&1
)
nssm restart brandflow-control-plane >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [警告] brandflow-control-plane 重启失败 >> "%LOG_FILE%" 2>&1
)

echo. >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1
echo  更新完成！ >> "%LOG_FILE%" 2>&1
echo  后端: http://127.0.0.1:17890 >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1
