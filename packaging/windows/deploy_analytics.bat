@echo off
chcp 65001 >nul
title 数据大屏 - 导出并部署到 GitHub Pages

set PROJECT_DIR=C:\Users\ziyua\Documents\Code\ai-video-pipeline
set DIST_DIR=%PROJECT_DIR%\frontend\dist
set PUBLISH_DIR=%PROJECT_DIR%\.publish-analytics
set SNAPSHOTS_DIR=%PROJECT_DIR%\data\snapshots

echo ========================================
echo  数据大屏 - 导出 + 部署到 GitHub Pages
echo ========================================

:: ── Environment checks ──────────────────────────────
echo.
echo [预备] 检查环境 ...
where git >nul 2>&1 || ( echo ERROR: 未找到 git, 请先安装 & pause & exit /b 1 )
where node >nul 2>&1 || ( echo ERROR: 未找到 Node.js & pause & exit /b 1 )
where npm >nul 2>&1 || ( echo ERROR: 未找到 npm & pause & exit /b 1 )
where uv >nul 2>&1 || ( echo ERROR: 未找到 uv & pause & exit /b 1 )
echo  环境检查通过

:: ── Step 1: git pull ───────────────────────────────
echo.
echo [1/6] 拉取最新代码 ...
cd /d "%PROJECT_DIR%"
git pull
if %errorlevel% neq 0 ( echo 拉取失败 & pause & exit /b 1 )

:: ── Step 2: 构建前端 ───────────────────────────────
echo.
echo [2/6] 构建前端 ...
cd /d "%PROJECT_DIR%\frontend"
call npm run build
if %errorlevel% neq 0 ( echo 构建失败 & pause & exit /b 1 )

:: ── Step 3: 保存快照 ──────────────────────────────
echo.
echo [3/6] 保存数据快照 + 导出 JSON ...
cd /d "%PROJECT_DIR%"
for /f %%i in ('wmic os get localtime ^| findstr [0-9]') do set DT=%%i
set TODAY=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%
uv run python tools\export_metrics_json.py --out "%DIST_DIR%" --save-snapshot %TODAY%
if %errorlevel% neq 0 ( echo 数据导出失败 & pause & exit /b 1 )

:: ── Step 4: 准备发布文件 ──────────────────────────
echo.
echo [4/6] 准备发布文件 ...
if exist "%PUBLISH_DIR%" rmdir /s /q "%PUBLISH_DIR%"
mkdir "%PUBLISH_DIR%"

:: 把 analytics.html 作为首页 index.html
copy "%DIST_DIR%\analytics.html" "%PUBLISH_DIR%\index.html" >nul 2>&1
copy "%DIST_DIR%\overview.json" "%PUBLISH_DIR%\" >nul 2>&1
copy "%DIST_DIR%\videos.json" "%PUBLISH_DIR%\" >nul 2>&1
copy "%DIST_DIR%\topics.json" "%PUBLISH_DIR%\" >nul 2>&1
copy "%DIST_DIR%\increment.json" "%PUBLISH_DIR%\" >nul 2>&1
copy "%DIST_DIR%\increment-detail.json" "%PUBLISH_DIR%\" >nul 2>&1
if exist "%DIST_DIR%\assets" (
    xcopy "%DIST_DIR%\assets" "%PUBLISH_DIR%\assets\" /e /i /q >nul
)

:: ── Step 5: 推送到 gh-pages ───────────────────────
echo.
echo [5/6] 推送到 GitHub gh-pages 分支 ...
cd /d "%PUBLISH_DIR%"
git init >nul
git checkout -b gh-pages >nul 2>&1
git add -A >nul
git commit -m "deploy: analytics snapshot %TODAY%" >nul
git remote add origin https://github.com/toRolex/ai-video-pipeline.git >nul 2>&1
git push -f origin gh-pages
if %errorlevel% neq 0 ( echo 部署推送失败 & pause & exit /b 1 )

:: ── Step 6: 清理 ──────────────────────────────────
echo.
echo [6/6] 清理临时文件 ...
rmdir /s /q "%PUBLISH_DIR%" >nul 2>&1

echo.
echo ============ 部署完成 ============
echo 访问地址:
echo https://torolex.github.io/ai-video-pipeline/
echo ==================================
echo.
pause
