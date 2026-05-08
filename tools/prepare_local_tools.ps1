param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$SkipWhisper
)

$ErrorActionPreference = "Stop"
$binDir = Join-Path $Root "tools\bin"
$modelDir = Join-Path $Root "tools\models"
$downloadDir = Join-Path $Root "tools\downloads"
New-Item -ItemType Directory -Force -Path $binDir, $modelDir, $downloadDir | Out-Null
$uv = (Get-Command uv -ErrorAction SilentlyContinue)
if (-not $uv) {
    throw "uv was not found. Install uv first: https://docs.astral.sh/uv/"
}
$uvExe = $uv.Source

function Download-File {
    param([string]$Url, [string]$OutFile)
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

function Copy-FirstMatch {
    param([string]$FromRoot, [string]$Pattern, [string]$Destination)
    $match = Get-ChildItem -Path $FromRoot -Recurse -File -Filter $Pattern | Select-Object -First 1
    if (-not $match) {
        throw "Cannot find $Pattern under $FromRoot"
    }
    Copy-Item -LiteralPath $match.FullName -Destination $Destination -Force
}

Write-Host "[1/4] Syncing Python dependencies with uv"
& $uvExe @("sync", "--project", $Root, "--locked")

$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
$ffprobeExe = Join-Path $binDir "ffprobe.exe"
if ((-not (Test-Path $ffmpegExe)) -or (-not (Test-Path $ffprobeExe))) {
    Write-Host "[2/4] Installing local FFmpeg"
    $ffmpegZip = Join-Path $downloadDir "ffmpeg-release-essentials.zip"
    if (-not (Test-Path $ffmpegZip)) {
        Download-File "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $ffmpegZip
    }
    $ffmpegExtract = Join-Path $downloadDir "ffmpeg"
    Remove-Item -LiteralPath $ffmpegExtract -Recurse -Force -ErrorAction SilentlyContinue
    Expand-Archive -LiteralPath $ffmpegZip -DestinationPath $ffmpegExtract -Force
    Copy-FirstMatch $ffmpegExtract "ffmpeg.exe" $ffmpegExe
    Copy-FirstMatch $ffmpegExtract "ffprobe.exe" $ffprobeExe
} else {
    Write-Host "[2/4] FFmpeg already installed locally"
}

if (-not $SkipWhisper) {
    $whisperExe = Join-Path $binDir "whisper-cli.exe"
    if (-not (Test-Path $whisperExe)) {
        Write-Host "[3/4] Installing local whisper.cpp CLI"
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/ggerganov/whisper.cpp/releases/latest" -Headers @{"User-Agent"="codex-local-setup"}
        $asset = $release.assets | Where-Object { $_.name -like "*bin*x64*.zip" -or $_.name -like "*whisper*x64*.zip" } | Select-Object -First 1
        if (-not $asset) {
            throw "Cannot find a Windows x64 whisper.cpp zip asset in the latest GitHub release."
        }
        $whisperZip = Join-Path $downloadDir $asset.name
        if (-not (Test-Path $whisperZip)) {
            Download-File $asset.browser_download_url $whisperZip
        }
        $whisperExtract = Join-Path $downloadDir "whisper"
        Remove-Item -LiteralPath $whisperExtract -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -LiteralPath $whisperZip -DestinationPath $whisperExtract -Force
        $releaseDir = Get-ChildItem -Path $whisperExtract -Directory -Recurse | Where-Object { Test-Path (Join-Path $_.FullName "whisper-cli.exe") } | Select-Object -First 1
        if (-not $releaseDir) {
            $cli = Get-ChildItem -Path $whisperExtract -Recurse -File | Where-Object { $_.Name -in @("whisper-cli.exe", "main.exe") } | Select-Object -First 1
            if ($cli) {
                $releaseDir = $cli.Directory
            }
        }
        if ($releaseDir) {
            Copy-Item -LiteralPath (Join-Path $releaseDir.FullName "*") -Destination $binDir -Recurse -Force
        }
        $cli = Get-ChildItem -Path $binDir -File | Where-Object { $_.Name -eq "whisper-cli.exe" } | Select-Object -First 1
        if (-not $cli) {
            throw "Cannot find whisper-cli.exe in $whisperZip"
        }
        if ($cli.FullName -ne $whisperExe) {
            Copy-Item -LiteralPath $cli.FullName -Destination $whisperExe -Force
        }
    } else {
        Write-Host "[3/4] whisper.cpp CLI already installed locally"
    }

    $modelPath = Join-Path $modelDir "ggml-small.bin"
    if (-not (Test-Path $modelPath)) {
        Write-Host "[4/4] Downloading Whisper small model"
        Download-File "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin" $modelPath
    } else {
        Write-Host "[4/4] Whisper model already installed locally"
    }
} else {
    Write-Host "[3/4] Whisper install skipped"
    Write-Host "[4/4] Whisper model skipped"
}

Write-Host ""
Write-Host "Local tools ready:"
Write-Host "  FFMPEG_PATH=$ffmpegExe"
Write-Host "  FFPROBE_PATH=$ffprobeExe"
Write-Host "  WHISPER_PATH=$(Join-Path $binDir "whisper-cli.exe")"
Write-Host "  MODEL_PATH=$(Join-Path $modelDir "ggml-small.bin")"
