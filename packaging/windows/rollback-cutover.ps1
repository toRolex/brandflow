$ErrorActionPreference = "Stop"

$projectDir = [System.IO.Path]::GetFullPath("D:\brandflow")
$liveVenv = Join-Path $projectDir ".venv"
$stagedVenv = Join-Path $projectDir ".venv-rollback"
$backupVenv = Join-Path $projectDir (".venv-pre-rollback-" + (Get-Date -Format "yyyyMMddHHmmss"))
$serviceName = "brandflow-control-plane"

if (-not (Test-Path -LiteralPath (Join-Path $stagedVenv "Scripts\python.exe"))) {
    throw "The prepared rollback environment is missing: $stagedVenv"
}
if (Test-Path -LiteralPath $backupVenv) {
    throw "The rollback backup path already exists: $backupVenv"
}

Write-Output "[rollback] Stopping $serviceName ..."
& sc.exe stop $serviceName | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Failed to stop $serviceName"
}

$stopped = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    $state = & sc.exe query $serviceName
    if ($state -match ":\s+1\s+") {
        $stopped = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $stopped) {
    throw "$serviceName did not stop within 30 seconds"
}

function Move-WithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,

        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    for ($attempt = 1; $attempt -le 15; $attempt++) {
        try {
            Move-Item -LiteralPath $Source -Destination $Destination -ErrorAction Stop
            return
        }
        catch {
            if ($attempt -eq 15) {
                throw
            }
            Start-Sleep -Seconds 1
        }
    }
}

if (Test-Path -LiteralPath $liveVenv) {
    Move-WithRetry -Source $liveVenv -Destination $backupVenv
}

try {
    Move-WithRetry -Source $stagedVenv -Destination $liveVenv
    Write-Output "[rollback] Starting $serviceName with rollback environment ..."
    & sc.exe start $serviceName | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start $serviceName"
    }
}
catch {
    Write-Output "[rollback] Cutover failed; restoring previous environment ..."
    if (Test-Path -LiteralPath $liveVenv) {
        Remove-Item -LiteralPath $liveVenv -Recurse -Force
    }
    if (Test-Path -LiteralPath $backupVenv) {
        Move-WithRetry -Source $backupVenv -Destination $liveVenv
        & sc.exe start $serviceName | Out-Host
    }
    throw
}

Write-Output "[rollback] Service cutover started successfully."
