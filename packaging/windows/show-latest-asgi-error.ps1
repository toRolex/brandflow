param(
    [string]$LogPath = "D:\brandflow\logs\control-plane.log"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $LogPath)) {
    exit 0
}

$lines = @(Get-Content -LiteralPath $LogPath -Tail 400)
$errorStart = -1
for ($index = $lines.Count - 1; $index -ge 0; $index--) {
    if ($lines[$index] -match "ERROR:.*ASGI application") {
        $errorStart = $index
        break
    }
}

if ($errorStart -lt 0) {
    exit 0
}

Write-Host "=== latest control-plane ASGI exception (up to 100 lines) ==="
$errorEnd = [Math]::Min($lines.Count - 1, $errorStart + 99)
$lines[$errorStart..$errorEnd]
