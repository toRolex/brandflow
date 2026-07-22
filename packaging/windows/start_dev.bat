@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 启动服务

set "PROJECT_DIR=%~dp0\..\.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

set "LOG_DIR=%PROJECT_DIR%\logs"
set "BACKEND_LOG=%LOG_DIR%\backend.log"
set "FRONTEND_LOG=%LOG_DIR%\frontend.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ============================================
echo  Brandflow 启动服务
echo  项目目录: %PROJECT_DIR%
echo  后端日志: %BACKEND_LOG%
echo  前端日志: %FRONTEND_LOG%
echo ============================================
echo.

:: --- 1. 检查运行环境 ---
echo [1/4] 检查运行环境 ...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 uv。请先运行 init.bat 或安装 uv: https://docs.astral.sh/uv/ >> "%BACKEND_LOG%"
    echo [错误] 未找到 uv。请先运行 init.bat 或安装 uv: https://docs.astral.sh/uv/
    echo 详情见日志: %BACKEND_LOG%
    pause
    exit /b 1
)
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Node.js。请安装 Node.js 20+ 或运行 setup-prereq.bat。 >> "%FRONTEND_LOG%"
    echo [错误] 未找到 Node.js。请安装 Node.js 20+ 或运行 setup-prereq.bat。
    echo 详情见日志: %FRONTEND_LOG%
    pause
    exit /b 1
)
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 npm。请安装 Node.js 20+。 >> "%FRONTEND_LOG%"
    echo [错误] 未找到 npm。请安装 Node.js 20+。
    echo 详情见日志: %FRONTEND_LOG%
    pause
    exit /b 1
)
if not exist "%PROJECT_DIR%\frontend\node_modules" (
    echo [错误] 前端依赖未安装。请在 frontend 目录执行: npm install >> "%FRONTEND_LOG%"
    echo [错误] 前端依赖未安装。请在 frontend 目录执行: npm install
    echo 详情见日志: %FRONTEND_LOG%
    pause
    exit /b 1
)
echo   环境检查通过。

if not exist "%PROJECT_DIR%\.env" (
    echo [警告] .env 不存在，服务将使用默认配置运行。真实生产环境请先配置 .env。
)

:: --- 2. 检查端口占用 ---
echo [2/4] 检查端口占用 ...
set "PORT_OK=1"
netstat -ano ^| findstr ":17890" >nul 2>&1 && (
    echo [错误] 端口 17890 已被占用。
    set PORT_OK=0
)
netstat -ano ^| findstr ":5173" >nul 2>&1 && (
    echo [错误] 端口 5173 已被占用。
    set PORT_OK=0
)
if %PORT_OK% equ 0 (
    echo 请先释放端口后再运行本脚本。
    pause
    exit /b 1
)
echo   端口可用。

:: --- 3. 启动后端 ---
echo [3/4] 启动后端（日志写入 %BACKEND_LOG%）...
echo [%date% %time%] 启动后端 ... > "%BACKEND_LOG%"
start /B "" cmd /c "cd /d %PROJECT_DIR% && uv run python -m apps.control_plane > %BACKEND_LOG% 2>&1"

:: --- 4. 启动前端 ---
echo [4/4] 启动前端（日志写入 %FRONTEND_LOG%）...
echo [%date% %time%] 启动前端 ... > "%FRONTEND_LOG%"
start /B "" cmd /c "cd /d %PROJECT_DIR%\frontend && npm run dev > %FRONTEND_LOG% 2>&1"

:: --- 5. 等待并验证 ---
echo   等待服务启动 ...
timeout /t 6 /nobreak >nul

set "BACKEND_OK=0"
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:17890/api/health 2>nul ^| findstr "200" >nul && set BACKEND_OK=1
if %BACKEND_OK% equ 0 (
    echo.
    echo [错误] 后端健康检查失败。
    echo        请查看日志: %BACKEND_LOG%
    echo        常见原因：端口冲突、.env 配置错误、依赖未安装。
    echo 正在尝试停止已启动的进程 ...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":17890"') do taskkill /PID %%a /F >nul 2>&1
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173"') do taskkill /PID %%a /F >nul 2>&1
    pause
    exit /b 1
)
echo   后端健康检查通过: http://127.0.0.1:17890/api/health

set "FRONTEND_OK=0"
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:5173 2>nul ^| findstr "200" >nul && set FRONTEND_OK=1
if %FRONTEND_OK% equ 0 (
    echo.
    echo [错误] 前端启动检查失败。
    echo        请查看日志: %FRONTEND_LOG%
    echo 正在尝试停止已启动的进程 ...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":17890"') do taskkill /PID %%a /F >nul 2>&1
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173"') do taskkill /PID %%a /F >nul 2>&1
    pause
    exit /b 1
)
echo   前端启动检查通过: http://127.0.0.1:5173

echo.
echo ============================================
echo  服务已启动
echo  后端: http://127.0.0.1:17890
echo  前端: http://127.0.0.1:5173
echo  后端日志: %BACKEND_LOG%
echo  前端日志: %FRONTEND_LOG%
echo ============================================
echo 按任意键停止服务 ...
pause >nul

:: --- 6. 停止服务 ---
echo 正在停止服务 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":17890"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173"') do taskkill /PID %%a /F >nul 2>&1
echo 服务已停止。
