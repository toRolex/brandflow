param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputPath) {
    $OutputPath = Join-Path $Root ".runtime_batch_direction.txt"
}
if (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $Root $OutputPath
}

$prompt = "Enter the rough direction for this batch of 10 scripts. Leave blank for default."
$title = "Batch direction"
$text = ""

try {
    Add-Type -AssemblyName Microsoft.VisualBasic
    $text = [Microsoft.VisualBasic.Interaction]::InputBox($prompt, $title, "")
}
catch {
    Write-Host "Batch direction popup failed; continuing with blank direction."
    $text = ""
}

[System.IO.File]::WriteAllText($OutputPath, ($text -as [string]), [System.Text.Encoding]::UTF8)
Write-Host ("Batch direction saved to " + $OutputPath)
