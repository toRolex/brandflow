[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^v\d+\.\d+\.\d+$')]
    [string]$ExpectedTag
)

$ErrorActionPreference = "Stop"
$projectDir = [System.IO.Path]::GetFullPath("D:\brandflow")
$sourceDir = [System.IO.Path]::GetFullPath($SourceDir)
$stagedVenv = Join-Path $projectDir ".venv-rollback"
$liveVenv = Join-Path $projectDir ".venv"
$backupVenv = Join-Path $projectDir (".venv-pre-rollback-" + (Get-Date -Format "yyyyMMddHHmmss"))
$logDir = Join-Path $projectDir "logs"
$stdoutLog = Join-Path $logDir "control-plane-rollback.log"
$stderrLog = Join-Path $logDir "control-plane-rollback-error.log"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

function Get-Health {
    try {
        return Invoke-RestMethod `
            -Uri "http://127.0.0.1:17890/api/health" `
            -TimeoutSec 2 `
            -Proxy $null
    }
    catch {
        return $null
    }
}

function Stop-BrandflowListener {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Health,

        [Parameter(Mandatory = $true)]
        [object[]]$Listeners
    )

    if ($Health.status -ne "ok" -or -not $Health.version) {
        throw "Port 17890 answered, but did not identify itself as a healthy Brandflow control plane"
    }

    $owners = @($Listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    Write-Host "Stopping Brandflow $($Health.version) on PID(s): $($owners -join ', ')"

    # The existing control plane runs the update helper under the service account.
    # Use that one-shot helper to grant NetworkService only start/stop rights.
    $requestFile = Join-Path $projectDir "packaging\windows\grant-service-control.request"
    $grantScript = Join-Path $projectDir "packaging\windows\grant-service-control.ps1"
    if (Test-Path -LiteralPath $grantScript) {
        Set-Content -LiteralPath $requestFile -Value "request"
        try {
            Invoke-WebRequest `
                -Uri "http://127.0.0.1:17890/api/update" `
                -Method Post `
                -UseBasicParsing `
                -TimeoutSec 10 `
                -Proxy $null | Out-Null
            for ($attempt = 1; $attempt -le 15; $attempt++) {
                if (-not (Test-Path -LiteralPath $requestFile)) {
                    break
                }
                Start-Sleep -Seconds 1
            }
        }
        catch {
            Write-Warning "Service-control grant request failed: $($_.Exception.Message)"
        }
    }

    & sc.exe stop brandflow-control-plane | Out-Host
    $serviceStopExit = $LASTEXITCODE
    if ($serviceStopExit -eq 0) {
        for ($attempt = 1; $attempt -le 30; $attempt++) {
            if (-not (Get-NetTCPConnection -LocalPort 17890 -State Listen -ErrorAction SilentlyContinue)) {
                return $false
            }
            Start-Sleep -Seconds 1
        }
    }

    # A prior emergency launch may be a standalone process rather than the
    # Windows service. Only stop it after proving both its module and path.
    foreach ($owner in $owners) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $owner"
        $expectedExecutableRoot = ($projectDir.TrimEnd("\") + "\").ToLowerInvariant()
        $executablePath = [string]$processInfo.ExecutablePath
        $commandLine = [string]$processInfo.CommandLine
        $isBrandflowProcess = (
            $executablePath -and
            $executablePath.ToLowerInvariant().StartsWith($expectedExecutableRoot) -and
            $commandLine -match "apps\.control_plane"
        )
        if (-not $isBrandflowProcess) {
            if ($serviceStopExit -ne 0 -and -not $executablePath) {
                Write-Host "The runner cannot inspect or stop the service process; elevated cutover is required."
                return $true
            }
            throw "Refusing to stop unverified listener PID $owner ($executablePath)"
        }
        Stop-Process -Id $owner -Force
    }

    Start-Sleep -Seconds 2
    if (Get-NetTCPConnection -LocalPort 17890 -State Listen -ErrorAction SilentlyContinue) {
        throw "Brandflow listener on port 17890 did not stop"
    }
    return $false
}

if (-not (Test-Path -LiteralPath (Join-Path $sourceDir ".git"))) {
    throw "Rollback source is not a Git checkout: $sourceDir"
}
if (-not (Test-Path -LiteralPath (Join-Path $sourceDir "pyproject.toml"))) {
    throw "Rollback source does not look like Brandflow: $sourceDir"
}
if (-not (Test-Path -LiteralPath (Join-Path $projectDir ".git"))) {
    throw "Production checkout is missing: $projectDir"
}

$resolvedTag = (& git -C $sourceDir describe --tags --exact-match HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $resolvedTag -ne $ExpectedTag) {
    throw "Rollback checkout is '$resolvedTag', expected '$ExpectedTag'"
}

$expectedVersion = $ExpectedTag.Substring(1)
$currentHealth = Get-Health
if (
    $null -ne $currentHealth -and
    $currentHealth.status -eq "ok" -and
    $currentHealth.version -eq $expectedVersion
) {
    Write-Host "Production is already healthy on $ExpectedTag."
    exit 0
}

$listeners = @(Get-NetTCPConnection -LocalPort 17890 -State Listen -ErrorAction SilentlyContinue)
$needsElevatedCutover = $false
if ($listeners.Count -gt 0) {
    if ($null -eq $currentHealth) {
        $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        throw "Port 17890 is owned by a non-Brandflow process: $owners"
    }
    $needsElevatedCutover = Stop-BrandflowListener -Health $currentHealth -Listeners $listeners
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Write-Host "Restoring production checkout to $ExpectedTag ..."
Push-Location $projectDir
try {
    $trackedStatus = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to inspect tracked production checkout changes"
    }
    if (@($trackedStatus).Count -gt 0) {
        throw "Production checkout has tracked local changes; refusing to overwrite runtime state"
    }
    Invoke-Native -FilePath git -Arguments @(
        "fetch",
        "--no-tags",
        "--update-shallow",
        $sourceDir,
        "HEAD"
    )
    Invoke-Native -FilePath git -Arguments @(
        "checkout",
        "--no-overwrite-ignore",
        "FETCH_HEAD"
    )
    $preservePatternsFile = Join-Path $PSScriptRoot "runtime-preserve-patterns.txt"
    if (-not (Test-Path -LiteralPath $preservePatternsFile)) {
        throw "Runtime preservation manifest is missing: $preservePatternsFile"
    }
    $cleanArguments = @("clean", "-fd")
    foreach ($pattern in Get-Content -LiteralPath $preservePatternsFile) {
        $trimmedPattern = $pattern.Trim()
        if ($trimmedPattern) {
            $cleanArguments += @("-e", $trimmedPattern)
        }
    }
    # Never pass -x here: ignored paths contain production runtime state.
    Invoke-Native -FilePath git -Arguments $cleanArguments

    $uvCandidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        "C:\Users\ziyua\.local\bin\uv.exe",
        "C:\Users\admin\.local\bin\uv.exe"
    )
    $uv = $uvCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $uv) {
        $uvCommand = Get-Command uv.exe -ErrorAction SilentlyContinue
        if ($uvCommand) {
            $uv = $uvCommand.Source
        }
    }
    if (-not $uv) {
        throw "uv.exe was not found on the production runner"
    }

    $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectDir ".uv-python"
    Invoke-Native -FilePath $uv -Arguments @("python", "install", "3.11")
    $python = (& $uv python find 3.11).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $python) {
        throw "Python 3.11 could not be resolved"
    }

    if (Test-Path -LiteralPath $stagedVenv) {
        Remove-Item -LiteralPath $stagedVenv -Recurse -Force
    }
    Invoke-Native -FilePath $uv -Arguments @(
        "venv",
        "--relocatable",
        "--python",
        $python,
        $stagedVenv
    )
    $env:UV_PROJECT_ENVIRONMENT = $stagedVenv
    try {
        Invoke-Native -FilePath $uv -Arguments @(
            "sync",
            "--python",
            $python,
            "--all-extras",
            "--dev"
        )
    }
    finally {
        Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue
    }

    $nodeDir = Join-Path $projectDir ".node\node-v20.18.3-win-x64"
    if (-not (Test-Path -LiteralPath (Join-Path $nodeDir "node.exe"))) {
        throw "The production Node.js 20 runtime is missing: $nodeDir"
    }
    $env:Path = "$nodeDir;$env:Path"
    $pnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if ($pnpm) {
        $pnpmFilePath = $pnpm.Source
        $pnpmPrefixArgs = @()
    }
    else {
        $npm = Join-Path $nodeDir "npm.cmd"
        if (-not (Test-Path -LiteralPath $npm)) {
            throw "Neither pnpm.cmd nor npm.cmd was found on the production runner"
        }

        # Node.js 20.18.3 bundles an older Corepack whose npm signing keys are
        # stale. Install a pinned, compatible Corepack through npm so pnpm's
        # signature remains verified instead of disabling integrity checks.
        $runnerTemp = $env:RUNNER_TEMP
        if (-not $runnerTemp) {
            $runnerTemp = $env:TEMP
        }
        $corepackTools = Join-Path $runnerTemp "brandflow-corepack-0.31.0"
        Invoke-Native -FilePath $npm -Arguments @(
            "install",
            "--global",
            "--prefix",
            $corepackTools,
            "--no-audit",
            "--no-fund",
            "--ignore-scripts",
            "corepack@0.31.0"
        )
        $corepack = Join-Path $corepackTools "corepack.cmd"
        if (-not (Test-Path -LiteralPath $corepack)) {
            throw "Pinned Corepack installation did not create: $corepack"
        }
        $pnpmFilePath = $corepack
        $pnpmPrefixArgs = @("pnpm@11.17.0")
    }

    Push-Location (Join-Path $projectDir "frontend")
    try {
        Invoke-Native -FilePath $pnpmFilePath -Arguments ($pnpmPrefixArgs + @(
            "install",
            "--no-frozen-lockfile"
        ))
        Invoke-Native -FilePath $pnpmFilePath -Arguments ($pnpmPrefixArgs + @("build"))
    }
    finally {
        Pop-Location
    }

    if (-not $needsElevatedCutover) {
        if (Test-Path -LiteralPath $backupVenv) {
            throw "Backup path already exists: $backupVenv"
        }
        if (Test-Path -LiteralPath $liveVenv) {
            Move-Item -LiteralPath $liveVenv -Destination $backupVenv
        }
        try {
            Move-Item -LiteralPath $stagedVenv -Destination $liveVenv
        }
        catch {
            if (Test-Path -LiteralPath $backupVenv) {
                Move-Item -LiteralPath $backupVenv -Destination $liveVenv
            }
            throw
        }
    }
}
finally {
    Pop-Location
}

if ($needsElevatedCutover) {
    Write-Host "Requesting elevated service cutover ..."
    $cutoverScript = Join-Path $logDir "rollback-cutover.ps1"
    Copy-Item `
        -LiteralPath (Join-Path $PSScriptRoot "rollback-cutover.ps1") `
        -Destination $cutoverScript `
        -Force

    $updateBat = Join-Path $projectDir "packaging\windows\update.bat"
    @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "$cutoverScript"
exit /b %errorlevel%
"@ | Set-Content -LiteralPath $updateBat -Encoding Ascii

    Invoke-WebRequest `
        -Uri "http://127.0.0.1:17890/api/update" `
        -Method Post `
        -UseBasicParsing `
        -TimeoutSec 10 `
        -Proxy $null | Out-Null

    $healthy = $false
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        Start-Sleep -Seconds 1
        $health = Get-Health
        if (
            $null -ne $health -and
            $health.status -eq "ok" -and
            $health.version -eq $expectedVersion
        ) {
            $healthy = $true
            break
        }
    }

    Push-Location $projectDir
    try {
        Invoke-Native -FilePath git -Arguments @(
            "checkout",
            "--",
            "packaging/windows/update.bat"
        )
    }
    finally {
        Pop-Location
        Remove-Item -LiteralPath $cutoverScript -Force -ErrorAction SilentlyContinue
    }

    if (-not $healthy) {
        throw "Elevated rollback did not become healthy on $ExpectedTag"
    }
    Write-Host "Production Windows service is healthy on $ExpectedTag."
    exit 0
}

Write-Host "Starting the rollback control-plane process ..."
$env:DEV_AUTO_TICK = "1"
$env:RUNNER_TRACKING_ID = "brandflow-rollback-" + [guid]::NewGuid().ToString("N")
$process = Start-Process `
    -FilePath (Join-Path $liveVenv "Scripts\python.exe") `
    -ArgumentList "-m", "apps.control_plane" `
    -WorkingDirectory $projectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

$healthy = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    Start-Sleep -Seconds 1
    $health = Get-Health
    if (
        $null -ne $health -and
        $health.status -eq "ok" -and
        $health.version -eq $expectedVersion
    ) {
        $healthy = $true
        break
    }
    if ($process.HasExited) {
        break
    }
}

if (-not $healthy) {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    throw "Rollback process did not become healthy on $ExpectedTag; see $stderrLog"
}

Set-Content -LiteralPath (Join-Path $logDir "rollback-process.pid") -Value $process.Id
Write-Host "Production is healthy on $ExpectedTag (PID $($process.Id))."
