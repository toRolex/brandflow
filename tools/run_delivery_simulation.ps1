param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ProjectName = "",
    [switch]$SkipToolInstall
)

$ErrorActionPreference = "Stop"
Push-Location $Root
try {
    $python = (Get-Command py -ErrorAction SilentlyContinue)
    if ($python) {
        $pythonExe = $python.Source
        $pythonArgs = @("-3.11")
    } else {
        $python = (Get-Command python -ErrorAction Stop)
        $pythonExe = $python.Source
        $pythonArgs = @()
    }

    if (-not $SkipToolInstall) {
        powershell -ExecutionPolicy Bypass -File "tools\prepare_local_tools.ps1" -Root $Root
    }

    if (-not $ProjectName) {
        $ProjectName = "001mock_acceptance_" + (Get-Date -Format "yyyyMMdd_HHmmss")
    }
    & $pythonExe @pythonArgs tools\create_mock_project.py --root . --name $ProjectName

    $env:PIPELINE_DRY_RUN = "0"
    $env:FFMPEG_PATH = Join-Path $Root "tools\bin\ffmpeg.exe"
    $env:FFPROBE_PATH = Join-Path $Root "tools\bin\ffprobe.exe"
    $env:WHISPER_PATH = Join-Path $Root "tools\bin\whisper-cli.exe"
    $env:MODEL_PATH = Join-Path $Root "tools\models\ggml-small.bin"
    if (-not $env:COVER_FONT_PATH) {
        $env:COVER_FONT_PATH = "C:\Windows\Fonts\simhei.ttf"
    }

    Write-Host "[probe] DeepSeek/LLM"
    & $pythonExe @pythonArgs main_controller.py --root . --check-llm --non-interactive
    Write-Host "[probe] MiMo/TTS"
    & $pythonExe @pythonArgs main_controller.py --root . --check-tts --non-interactive

    Write-Host "[run] generating 10 deliverable videos"
    & $pythonExe @pythonArgs main_controller.py --root . --host 127.0.0.1 --port 17890 --batch-size 10 --non-interactive --stop-after-completed 10 --max-runtime-seconds 1800

    Write-Host "[validate] delivery acceptance"
    & $pythonExe @pythonArgs tools\validate_delivery.py --root . --project $ProjectName --expected 10
} finally {
    Pop-Location
}
