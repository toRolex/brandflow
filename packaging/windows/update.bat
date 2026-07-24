@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Brandflow — 快速更新

set "PROJECT_DIR=%~dp0..\.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

set "LOG_FILE=%~dp0update.log"
set "PROGRESS_FILE=%~dp0progress.json"

echo ============================================ >> "%LOG_FILE%" 2>&1
echo  Brandflow 快速更新 >> "%LOG_FILE%" 2>&1
echo  1. 拉取最新代码 >> "%LOG_FILE%" 2>&1
echo  2. 更新 Python 依赖 >> "%LOG_FILE%" 2>&1
echo  3. 编译前端 >> "%LOG_FILE%" 2>&1
echo  4. 重启控制面 >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1

:: 初始进度（后端已写入初始状态，这里覆盖第一步）
echo {"status":"running","step":"git_pull","step_label":"拉取最新代码","percent":5,"updated_at":"%date% %time%"} > "%PROGRESS_FILE%"

:: ── 1. 拉取最新代码 ──
echo [1/4] 拉取最新代码 ... >> "%LOG_FILE%" 2>&1
git pull >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [错误] git pull 失败 >> "%LOG_FILE%" 2>&1
    echo {"status":"failed","step":"git_pull","step_label":"拉取最新代码","percent":5,"error":"git pull 失败","updated_at":"%date% %time%"} > "%PROGRESS_FILE%"
    exit /b %errorlevel%
)
echo {"status":"running","step":"uv_sync","step_label":"更新 Python 依赖","percent":25,"updated_at":"%date% %time%"} > "%PROGRESS_FILE%"

:: ── 2. 更新 Python 依赖 ──
echo [2/4] 更新 Python 依赖 ... >> "%LOG_FILE%" 2>&1
uv sync --all-extras --dev >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [错误] uv sync 失败 >> "%LOG_FILE%" 2>&1
    echo {"status":"failed","step":"uv_sync","step_label":"更新 Python 依赖","percent":25,"error":"uv sync 失败","updated_at":"%date% %time%"} > "%PROGRESS_FILE%"
    exit /b %errorlevel%
)
echo {"status":"running","step":"pnpm_install","step_label":"安装前端依赖","percent":50,"updated_at":"%date% %time%"} > "%PROGRESS_FILE%"

:: ── 3. 编译前端 ──
echo [3/4] 编译前端 ... >> "%LOG_FILE%" 2>&1
pushd "%PROJECT_DIR%\frontend"
call pnpm install --no-frozen-lockfile >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [错误] pnpm install 失败 >> "%LOG_FILE%" 2>&1
    echo {"status":"failed","step":"pnpm_install","step_label":"安装前端依赖","percent":50,"error":"pnpm install 失败","updated_at":"%date% %time%"} > "%PROGRESS_FILE%"
    popd
    exit /b %errorlevel%
)
echo {"status":"running","step":"pnpm_build","step_label":"编译前端","percent":90,"updated_at":"%date% %time%"} > "%PROGRESS_FILE%"

call pnpm build >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [错误] pnpm build 失败 >> "%LOG_FILE%" 2>&1
    echo {"status":"failed","step":"pnpm_build","step_label":"编译前端","percent":90,"error":"pnpm build 失败","updated_at":"%date% %time%"} > "%PROGRESS_FILE%"
    popd
    exit /b %errorlevel%
)
popd

:: ── 4. 重启控制面 ──
echo [4/4] 重启控制面 ... >> "%LOG_FILE%" 2>&1

:: 检查 nssm 是否可用
set "NSSM_CMD=nssm"
where nssm >nul 2>&1 || (
    if not exist "%PROJECT_DIR%\tools\nssm-2.24\win64\nssm.exe" (
        echo [警告] nssm 未找到，跳过控制面重启 >> "%LOG_FILE%" 2>&1
        echo {"status":"done","step":"done","step_label":"更新完成","percent":100,"updated_at":"%date% %time%"} > "%PROGRESS_FILE%"
        goto :done
    )
    set "NSSM_CMD=%PROJECT_DIR%\tools\nssm-2.24\win64\nssm.exe"
)

echo {"status":"restarting","step":"restart_cp","step_label":"重启控制面","percent":95,"updated_at":"%date% %time%"} > "%PROGRESS_FILE%"

:: 安全重启：延迟 3 秒后由独立进程执行 nssm restart，保证本脚本先优雅退出
start /b cmd /c "timeout /t 3 /nobreak >nul && "!NSSM_CMD!" restart brandflow-control-plane >> "%LOG_FILE%" 2>&1"

echo {"status":"done","step":"done","step_label":"更新完成","percent":100,"updated_at":"%date% %time%"} > "%PROGRESS_FILE%"

:done
echo. >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1
echo  更新完成 >> "%LOG_FILE%" 2>&1
echo  后端: http://127.0.0.1:17890 >> "%LOG_FILE%" 2>&1
echo ============================================ >> "%LOG_FILE%" 2>&1
