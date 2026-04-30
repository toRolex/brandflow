param(
    [ValidateSet("Env", "Materials", "Media")]
    [string]$Mode
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($Mode -eq "Env") {
    $envPath = Join-Path $Root ".env"
    if (-not (Test-Path $envPath)) {
        Write-Host "Missing .env"
        exit 2
    }
    $text = Get-Content $envPath -Raw -Encoding UTF8
    $required = @("DEEPSEEK_API_KEY", "MIMO_API_KEY")
    $missing = @()
    foreach ($key in $required) {
        if ($text -notmatch ("(?m)^" + [regex]::Escape($key) + "=.")) {
            $missing += $key
        }
    }
    if ($missing.Count -gt 0) {
        Write-Host ("Missing keys: " + ($missing -join ", "))
        exit 2
    }
    exit 0
}

if ($Mode -eq "Materials") {
    $rawFolderName = ([string][char]0x539f) + ([string][char]0x7d20) + ([string][char]0x6750)
    $projectNamePattern = '^\d{3}.+'
    $projects = Get-ChildItem -Path $Root -Directory | Where-Object {
        $raw = Join-Path $_.FullName $rawFolderName
        ($_.Name -match $projectNamePattern) -and (Test-Path $raw) -and (Get-ChildItem $raw -File -ErrorAction SilentlyContinue | Select-Object -First 1)
    }
    if (-not $projects) {
        exit 2
    }
    exit 0
}

if ($Mode -eq "Media") {
    $errors = @()
    $subtitleMode = if ($env:SUBTITLE_MODE) { $env:SUBTITLE_MODE.ToLowerInvariant() } else { "script_timed" }
    $ffmpeg = if ($env:FFMPEG_PATH) { $env:FFMPEG_PATH } else { Join-Path $Root "tools\bin\ffmpeg.exe" }
    $ffprobe = if ($env:FFPROBE_PATH) { $env:FFPROBE_PATH } else { Join-Path $Root "tools\bin\ffprobe.exe" }
    $whisper = if ($env:WHISPER_PATH) { $env:WHISPER_PATH } else { Join-Path $Root "tools\bin\whisper-cli.exe" }
    $model = if ($env:MODEL_PATH) { $env:MODEL_PATH } else { Join-Path $Root "tools\models\ggml-small.bin" }

    if (-not (Test-Path $ffmpeg)) {
        $errors += "Missing ffmpeg: $ffmpeg"
    }
    if (-not (Test-Path $ffprobe)) {
        $errors += "Missing ffprobe: $ffprobe"
    }
    if ($subtitleMode -eq "whisper") {
        if (-not (Test-Path $whisper)) {
            $errors += "Missing whisper: $whisper"
        }
        if (-not (Test-Path $model)) {
            $errors += "Missing whisper model: $model"
        }
        if (-not [Text.Encoding]::ASCII.GetString([Text.Encoding]::ASCII.GetBytes($whisper)).Equals($whisper)) {
            $errors += "WHISPER_PATH contains non-ASCII characters: $whisper"
        }
        if (-not [Text.Encoding]::ASCII.GetString([Text.Encoding]::ASCII.GetBytes($model)).Equals($model)) {
            $errors += "MODEL_PATH contains non-ASCII characters: $model"
        }
    }

    if ($errors.Count -gt 0) {
        foreach ($item in $errors) {
            Write-Host $item
        }
        exit 2
    }
    exit 0
}
