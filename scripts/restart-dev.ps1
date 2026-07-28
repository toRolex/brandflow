#!/usr/bin/env pwsh
#Requires -Version 7.0
<#
.SYNOPSIS
    拉取最新代码并重新启动 Brandflow 前后端开发环境。

.DESCRIPTION
    默认单次运行：
      1. git pull 更新当前分支
      2. 安装/同步依赖（uv sync + pnpm install）
      3. 结束已占用的前后端进程（17890 / 5173）
      4. 重新启动后端 control_plane 与前端 Vite dev server
      5. 可选自动打开浏览器

    守护模式（-Watch）：
      脚本会持续运行，每隔 IntervalSeconds 秒尝试拉取代码；
      只有在实际发生代码更新时才会重启前后端。
      本地未提交更改会自动 stash，拉取完成后自动 pop。
      任何步骤出错都会记录并继续下一轮，不会退出。

.PARAMETER Watch
    启用守护模式，持续监控代码更新并自动重启服务。

.PARAMETER IntervalSeconds
    守护模式下每次检查间隔，默认 30 秒。

.PARAMETER SkipInitialStart
    守护模式下跳过首次启动，进入循环后再按需启动。

.PARAMETER SkipPull
    单次模式下跳过 git pull（守护模式下无效）。

.PARAMETER SkipDeps
    跳过依赖同步。

.PARAMETER NoBrowser
    启动完成后不自动打开浏览器。

.PARAMETER BackendPort
    后端端口，默认 17890。

.PARAMETER FrontendPort
    前端端口，默认 5173。

.EXAMPLE
    .\scripts\restart-dev.ps1
    .\scripts\restart-dev.ps1 -SkipPull -NoBrowser
    .\scripts\restart-dev.ps1 -Watch
    .\scripts\restart-dev.ps1 -Watch -IntervalSeconds 60 -SkipInitialStart
#>

[CmdletBinding()]
param(
    [switch]$Watch,
    [int]$IntervalSeconds = 30,
    [switch]$SkipInitialStart,
    [switch]$SkipPull,
    [switch]$SkipDeps,
    [switch]$NoBrowser,
    [int]$BackendPort = 17890,
    [int]$FrontendPort = 5173
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ROOT = Split-Path -Parent $PSScriptRoot
$LOGS_DIR = Join-Path $ROOT "logs"
$BACKEND_LOG = Join-Path $LOGS_DIR "control_plane.log"
$FRONTEND_LOG = Join-Path $LOGS_DIR "frontend.log"

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-PowerShellExecutable {
    if (Test-CommandAvailable "pwsh") { return "pwsh" }
    if (Test-CommandAvailable "powershell") { return "powershell" }
    throw "未找到 pwsh 或 powershell，请先安装 PowerShell。"
}

$PS_EXECUTABLE = Get-PowerShellExecutable

function Stop-ProcessOnPort {
    param([int]$Port, [string]$Label)
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq "Listen" -or $_.State -eq "Established" }
        if (-not $conns) { return }
        $procIds = $conns | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $procIds) {
            try {
                $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
                if ($proc) {
                    Write-Host "  正在结束 $Label 进程 PID=$procId ($($proc.ProcessName))" -ForegroundColor Yellow
                    Stop-Process -Id $procId -Force
                }
            }
            catch {
                Write-Warning "无法结束端口 $Port 上的进程 $procId`: $_"
            }
        }
    }
    catch {
        Write-Warning "查询端口 $Port 占用失败: $_"
    }
}

function Sync-Dependencies {
    if ($SkipDeps) {
        Write-Host "  跳过依赖同步。" -ForegroundColor DarkGray
        return
    }

    if (Test-CommandAvailable "uv") {
        Write-Host "  uv sync --no-dev ..."
        uv sync --no-dev
        if ($LASTEXITCODE -ne 0) { throw "uv sync 失败" }
    }
    else {
        Write-Warning "未找到 uv，跳过 Python 依赖同步。"
    }

    $frontendDir = Join-Path $ROOT "frontend"
    if (Test-CommandAvailable "pnpm") {
        Write-Host "  pnpm install (frontend) ..."
        Push-Location $frontendDir
        try {
            pnpm install
            if ($LASTEXITCODE -ne 0) { throw "pnpm install 失败" }
        }
        finally {
            Pop-Location
        }
    }
    elseif (Test-CommandAvailable "npm") {
        Write-Warning "未找到 pnpm，使用 npm install 作为回退。"
        Push-Location $frontendDir
        try {
            npm install
            if ($LASTEXITCODE -ne 0) { throw "npm install 失败" }
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Warning "未找到 pnpm 或 npm，跳过前端依赖同步。"
    }
}

function Restart-BrandflowServices {
    [CmdletBinding()]
    param()

    Write-Host ""
    Write-Host "===== 重启前后端服务 =====" -ForegroundColor Cyan

    # 1. 清理旧进程
    Write-Host "[1/3] 清理已有前后端进程 ..." -ForegroundColor Cyan
    Stop-ProcessOnPort -Port $BackendPort -Label "后端"
    Stop-ProcessOnPort -Port $FrontendPort -Label "前端"
    Start-Sleep -Seconds 1
    Write-Host "  清理完成。" -ForegroundColor Green

    # 2. 同步依赖
    Write-Host "[2/3] 同步依赖 ..." -ForegroundColor Cyan
    Sync-Dependencies
    Write-Host "  依赖同步完成。" -ForegroundColor Green

    # 3. 启动后端
    Write-Host "[3/3] 启动后端 (端口 $BackendPort) ..." -ForegroundColor Cyan
    $backendCmd = "uv run python -m apps.control_plane"
    $backendInfo = Start-Process `
        -FilePath $PS_EXECUTABLE `
        -ArgumentList "-NoProfile", "-Command", "$backendCmd *> `"$BACKEND_LOG`"" `
        -WorkingDirectory $ROOT `
        -WindowStyle Hidden `
        -PassThru
    Write-Host "  后端 PID: $($backendInfo.Id)，日志: $BACKEND_LOG" -ForegroundColor Green

    # 4. 启动前端
    Write-Host "      启动前端 (端口 $FrontendPort) ..." -ForegroundColor Cyan
    $frontendDir = Join-Path $ROOT "frontend"
    $frontendCmd = "pnpm dev"
    if (-not (Test-CommandAvailable "pnpm")) {
        $frontendCmd = "npm run dev"
    }
    $frontendInfo = Start-Process `
        -FilePath $PS_EXECUTABLE `
        -ArgumentList "-NoProfile", "-Command", "$frontendCmd *> `"$FRONTEND_LOG`"" `
        -WorkingDirectory $frontendDir `
        -WindowStyle Hidden `
        -PassThru
    Write-Host "  前端 PID: $($frontendInfo.Id)，日志: $FRONTEND_LOG" -ForegroundColor Green

    # 等待后端就绪
    Write-Host ""
    Write-Host "等待后端就绪 ..." -ForegroundColor Cyan
    $maxWait = 30
    $ready = $false
    for ($i = 0; $i -lt $maxWait; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                $ready = $true
                break
            }
        }
        catch { }
        Start-Sleep -Seconds 1
    }

    Write-Host ""
    if ($ready) {
        Write-Host "✅ 后端已就绪: http://127.0.0.1:$BackendPort" -ForegroundColor Green
    }
    else {
        Write-Warning "后端在 ${maxWait}s 内未响应，请检查 $BACKEND_LOG"
    }

    Write-Host "✅ 前端开发服务器: http://127.0.0.1:$FrontendPort" -ForegroundColor Green

    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:$FrontendPort"
    }
}

function Invoke-GitPullWithStash {
    [CmdletBinding()]
    param()

    if (-not (Test-CommandAvailable "git")) {
        throw "未找到 git 命令。"
    }

    $stashName = "watch-dev-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    $stashed = $false

    # 尝试暂存本地更改
    try {
        $null = git stash push -u -m "$stashName" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $stashed = $true
            Write-Host "  已自动暂存本地更改: $stashName" -ForegroundColor DarkYellow
        }
        else {
            Write-Host "  没有本地更改需要暂存。" -ForegroundColor DarkGray
        }
    }
    catch {
        Write-Warning "暂存本地更改失败: $_"
    }

    # 记录拉取前的 HEAD
    $before = $null
    try {
        $before = git rev-parse HEAD 2>&1
    }
    catch {
        Write-Warning "获取当前 HEAD 失败: $_"
    }

    # 拉取
    try {
        Write-Host "  git pull --rebase ..."
        git pull --rebase 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "git pull --rebase 返回非零退出码: $LASTEXITCODE"
        }
    }
    catch {
        Write-Warning "git pull 失败: $_"
    }

    # 恢复暂存
    if ($stashed) {
        try {
            Write-Host "  恢复暂存的本地更改 ..."
            git stash pop 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  已恢复暂存的本地更改。" -ForegroundColor Green
            }
            else {
                Write-Warning "恢复暂存失败（可能存在冲突），请手动处理: git stash list"
            }
        }
        catch {
            Write-Warning "恢复暂存异常: $_"
        }
    }

    # 判断是否有更新
    $after = $null
    try {
        $after = git rev-parse HEAD 2>&1
    }
    catch {
        Write-Warning "获取拉取后 HEAD 失败: $_"
    }

    return ($before -and $after -and ($before -ne $after))
}

function Start-WatchLoop {
    [CmdletBinding()]
    param()

    if (-not $SkipInitialStart) {
        Write-Host ""
        Write-Host "首次启动服务 ..." -ForegroundColor Cyan
        try {
            $ErrorActionPreference = "Continue"
            Restart-BrandflowServices
        }
        catch {
            Write-Warning "首次启动失败: $_"
            Write-Warning "将在下一轮重试。"
        }
    }

    Write-Host ""
    Write-Host "进入守护模式，每 $IntervalSeconds 秒检查一次代码更新。按 Ctrl+C 停止。" -ForegroundColor Cyan
    Write-Host ""

    while ($true) {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Write-Host "[$timestamp] 检查代码更新 ..." -ForegroundColor Cyan

        try {
            $ErrorActionPreference = "Continue"
            $updated = Invoke-GitPullWithStash
            if ($updated) {
                Write-Host "[$timestamp] 检测到代码更新，准备重启服务 ..." -ForegroundColor Green
                Restart-BrandflowServices
            }
            else {
                Write-Host "[$timestamp] 无更新。" -ForegroundColor DarkGray
            }
        }
        catch {
            Write-Warning "[$timestamp] 本轮检查失败: $_"
            Write-Warning "[$timestamp] 将在 $IntervalSeconds 秒后重试。"
        }

        Start-Sleep -Seconds $IntervalSeconds
    }
}

# ==================== 入口 ====================

Set-Location $ROOT
New-Item -ItemType Directory -Path $LOGS_DIR -Force | Out-Null

Write-Host "====================================" -ForegroundColor Cyan
Write-Host " Brandflow 开发环境管理脚本" -ForegroundColor Cyan
Write-Host " 项目根目录: $ROOT" -ForegroundColor Cyan
if ($Watch) {
    Write-Host " 模式: 守护模式（间隔 ${IntervalSeconds}s）" -ForegroundColor Cyan
}
else {
    Write-Host " 模式: 单次运行" -ForegroundColor Cyan
}
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

if ($Watch) {
    Start-WatchLoop
}
else {
    $ErrorActionPreference = "Stop"
    if (-not $SkipPull) {
        Write-Host "[1/2] 拉取最新代码 ..." -ForegroundColor Cyan
        $updated = Invoke-GitPullWithStash
        if ($updated) {
            Write-Host "  代码已更新。" -ForegroundColor Green
        }
        else {
            Write-Host "  代码已是最新。" -ForegroundColor Green
        }
    }
    Restart-BrandflowServices

    Write-Host ""
    Write-Host "按 Ctrl+C 停止本脚本不会结束已启动的子进程。" -ForegroundColor DarkYellow
    Write-Host "需要停止时，可再次运行本脚本，或手动结束端口 $BackendPort / $FrontendPort 上的进程。" -ForegroundColor DarkYellow
    Write-Host ""
    Write-Host "按 Enter 键退出此窗口 ..."
    [void][System.Console]::ReadLine()
}
