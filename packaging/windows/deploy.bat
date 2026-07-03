@echo off
chcp 65001 >nul
title Brandflow — 部署脚本
setlocal enabledelayedexpansion

set PROJECT_DIR=%~dp0..\..
pushd "%PROJECT_DIR%"
set PROJECT_DIR=%CD%
popd

set LOG_FILE=%PROJECT_DIR%\logs\deploy.log
if not exist "%PROJECT_DIR%\logs\" mkdir "%PROJECT_DIR%\logs\"

echo [%date% %time%] ========== 开始部署 ========== >> "%LOG_FILE%"

:: ---- Step 1: 前置检查 ----
echo [1/8] 检查前置工具...
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 uv，请先运行 setup-prereq.bat >> "%LOG_FILE%"
    echo [错误] 未找到 uv，请先运行 setup-prereq.bat
    exit /b 1
)
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 NSSM，请先运行 setup-prereq.bat >> "%LOG_FILE%"
    echo [错误] 未找到 NSSM，请先运行 setup-prereq.bat
    exit /b 1
)
where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    call nvm use 20.18.3 >nul 2>&1
    where pnpm >nul 2>&1
    if !errorlevel! neq 0 (
        echo [错误] 未找到 pnpm，请先运行 setup-prereq.bat >> "%LOG_FILE%"
        echo [错误] 未找到 pnpm，请先运行 setup-prereq.bat
        exit /b 1
    )
)
echo   全部工具就绪。

:: ---- Step 2: 部署前标记（用于回滚）----
echo [2/8] 打部署标记...
git tag -a deploy-%date:~0,4%%date:~5,2%%date:~8,2%-%time:~0,2%%time:~3,2%%time:~6,2% -m "deploy before update" >nul 2>&1

:: ---- Step 3: 拉取最新代码 ----
echo [3/8] 拉取最新代码...
git fetch --tags
git pull
if %errorlevel% neq 0 (
    echo [错误] git pull 失败 >> "%LOG_FILE%"
    exit /b 1
)

:: ---- Step 4: 安装依赖 ----
echo [4/8] 安装 Python 依赖...
uv sync --all-extras --dev
if %errorlevel% neq 0 (
    echo [错误] uv sync 失败 >> "%LOG_FILE%"
    exit /b 1
)

echo [5/8] 安装前端依赖并编译...
cd frontend
call nvm use 20.18.3 2>nul
pnpm install --no-frozen-lockfile
if %errorlevel% neq 0 (
    echo [错误] pnpm install 失败 >> "%LOG_FILE%"
    popd & exit /b 1
)
pnpm build
if %errorlevel% neq 0 (
    echo [错误] pnpm build 失败 >> "%LOG_FILE%"
    popd & exit /b 1
)
cd "%PROJECT_DIR%"

:: ---- Step 5: 检查 .env ----
echo [6/8] 检查环境变量文件...
if not exist "%PROJECT_DIR%\.env" (
    if exist "%PROJECT_DIR%\.env.example" (
        echo   .env 不存在，从 .env.example 复制...
        copy "%PROJECT_DIR%\.env.example" "%PROJECT_DIR%\.env" >nul
        echo   请手动编辑 .env 填入 API Key 后重新执行本脚本
        pause
        exit /b 1
    ) else (
        echo [错误] .env 和 .env.example 都不存在 >> "%LOG_FILE%"
        exit /b 1
    )
)

:: ---- Step 6: 重启服务 ----
echo [7/8] 重启服务...
nssm restart brandflow-control-plane
if %errorlevel% neq 0 (
    nssm start brandflow-control-plane
)
nssm restart brandflow-worker
if %errorlevel% neq 0 (
    nssm start brandflow-worker
)

:: ---- Step 7: 健康检查 + 回滚 ----
echo [8/8] 健康检查...
timeout /t 5 /nobreak >nul

curl -f http://127.0.0.1:17890/api/health >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 健康检查失败，触发回滚... >> "%LOG_FILE%"

    :: 获取上一个部署 tag
    for /f "delims=" %%t in ('git tag --sort=-creatordate ^| findstr "deploy-" ^| more +1') do (
        set ROLLBACK_TAG=%%t
        goto :rollback
    )
    :rollback
    if defined ROLLBACK_TAG (
        echo   回滚到 !ROLLBACK_TAG! ... >> "%LOG_FILE%"
        git reset --hard !ROLLBACK_TAG!
        uv sync --all-extras --dev >nul
        nssm restart brandflow-control-plane
        nssm restart brandflow-worker
        echo [完成] 已回滚到 !ROLLBACK_TAG! >> "%LOG_FILE%"
    ) else (
        echo [错误] 找不到可回滚的标记，请手动处理 >> "%LOG_FILE%"
    )
    exit /b 1
)

:: ---- 清理历史 tag（保留最近 10 个）----
for /f "skip=10 delims=" %%t in ('git tag --sort=-creatordate ^| findstr "deploy-"') do (
    git tag -d %%t >nul
)

echo [%date% %time%] ========== 部署成功 ========== >> "%LOG_FILE%"
echo 部署成功！
