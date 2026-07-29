$ErrorActionPreference = "Stop"

$serviceName = "brandflow-control-plane"
$networkServiceStartStopAce = "(A;;RPWP;;;NS)"

$output = & sc.exe sdshow $serviceName 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Failed to read the $serviceName service ACL: $output"
}

$sddl = $output |
    Where-Object { $_ -is [string] -and $_.TrimStart().StartsWith("D:") } |
    Select-Object -First 1
if (-not $sddl) {
    throw "The $serviceName service DACL was not found"
}

$sddl = $sddl.Trim()
if ($sddl.Contains($networkServiceStartStopAce)) {
    exit 0
}

$saclIndex = $sddl.IndexOf("S:", [System.StringComparison]::Ordinal)
if ($saclIndex -ge 0) {
    $updatedSddl = $sddl.Insert($saclIndex, $networkServiceStartStopAce)
} else {
    $updatedSddl = $sddl + $networkServiceStartStopAce
}

& sc.exe sdset $serviceName $updatedSddl
if ($LASTEXITCODE -ne 0) {
    throw "Failed to grant NetworkService start/stop access to $serviceName"
}
