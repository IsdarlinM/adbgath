[CmdletBinding()]
param([switch]$KeepWorkspace)
$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\adbgath"
$pathsToRemove = @((Join-Path $InstallRoot "bin"), (Join-Path $InstallRoot "platform-tools"))
$current = [Environment]::GetEnvironmentVariable("Path", "User")
$parts = @($current -split ';' | Where-Object { $_ -and $_.Trim() })
$filtered = $parts | Where-Object {
    $candidate = $_.TrimEnd('\')
    -not ($pathsToRemove | Where-Object { $candidate -ieq $_.TrimEnd('\') })
}
[Environment]::SetEnvironmentVariable("Path", ($filtered -join ';'), "User")
[Environment]::SetEnvironmentVariable("ADB_PATH", $null, "User")
[Environment]::SetEnvironmentVariable("ADBGATH_HOME", $null, "User")
if (Test-Path $InstallRoot) { Remove-Item $InstallRoot -Recurse -Force }
if (-not $KeepWorkspace) {
    $workspace = Join-Path $HOME "adbgath-workspace"
    if (Test-Path $workspace) { Remove-Item $workspace -Recurse -Force }
}
Write-Host "adbgath was removed. Open a new terminal to refresh PATH." -ForegroundColor Green
