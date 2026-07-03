@echo off
chcp 65001 >nul
title Brandflow — 前置工具安装
echo ============================================
echo  Brandflow 短视频自动化系统 — 前置工具安装
echo ============================================
echo.
echo 此脚本为一次性安装，需要管理员权限。
echo.

:: --- 检查管理员权限 ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 需要管理员权限运行此脚本。
    echo 请右键点击此脚本，选择"以管理员身份运行"。
    pause
    exit /b 1
)

:: --- 检查/安装 uv ---
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/6] 正在安装 uv...
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
) else (
    echo [1/6] uv 已安装，跳过
)

:: --- 检查/安装 nvm-windows ---
where nvm >nul 2>&1
if %errorlevel% neq 0 (
    echo [2/6] 正在安装 nvm-windows...
    powershell -c "Invoke-WebRequest -Uri https://github.com/coreybutler/nvm-windows/releases/download/1.2.2/nvm-setup.exe -OutFile %TEMP%\nvm-setup.exe"
    start /wait "" "%TEMP%\nvm-setup.exe" /S
) else (
    echo [2/6] nvm 已安装，跳过
)

:: --- 通过 nvm 安装 Node.js v20 LTS ---
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [3/6] 安装 Node.js v20 LTS（通过 nvm）...
    nvm install 20.18.3
    nvm use 20.18.3
) else (
    for /f "tokens=*" %%a in ('node -v') do set NODE_VER=%%a
    echo [3/6] Node.js %NODE_VER% 已安装，跳过
)

:: --- 安装 pnpm ---
where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo [4/6] 正在安装 pnpm...
    powershell -c "iwr https://get.pnpm.io/install.ps1 -useb | iex"
) else (
    echo [4/6] pnpm 已安装，跳过
)

:: --- 安装 FFmpeg ---
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo [5/6] 正在安装 FFmpeg...
    winget install --id Gyan.FFmpeg -e
) else (
    echo [5/6] FFmpeg 已安装，跳过
)

:: --- 安装 NSSM ---
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo [6/6] 正在安装 NSSM...
    winget install --id NSSM.NSSM -e
) else (
    echo [6/6] NSSM 已安装，跳过
)

echo.
echo ============================================
echo  安装完成！请关闭并重新打开终端。
echo  然后运行 setup-nssm.bat 注册服务。
echo ============================================
pause
