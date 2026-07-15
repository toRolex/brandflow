@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 快速更新

set "PROJECT_DIR=%~dp0..\.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

echo ============================================
echo  Brandflow 快速更新
echo  1. 拉取最新代码
echo  2. 编译前端
echo  3. 重启后端服务
echo ============================================
echo.

:: --- 1. 拉取最新代码 ---
echo [1/3] 拉取最新代码 ...
git pull
if %errorlevel% neq 0 (
    echo [错误] git pull 失败，请检查网络或冲突
    pause
    exit /b 1
)
echo   完成。

:: --- 2. 编译前端 ---
echo [2/3] 编译前端 ...
pushd "%PROJECT_DIR%\frontend"
call pnpm install --no-frozen-lockfile
if %errorlevel% neq 0 (
    echo [错误] pnpm install 失败
    popd & pause & exit /b 1
)
call pnpm build
if %errorlevel% neq 0 (
    echo [错误] pnpm build 失败
    popd & pause & exit /b 1
)
popd
echo   完成。

:: --- 3. 重启后端服务 ---
echo [3/3] 重启后端服务 ...
nssm restart brandflow-control-plane
if %errorlevel% neq 0 (
    echo [错误] nssm restart 失败，尝试 nssm start ...
    nssm start brandflow-control-plane
)
echo   完成。

echo.
echo ============================================
echo  更新完成！
echo  后端: http://127.0.0.1:17890
echo ============================================
echo.
pause
