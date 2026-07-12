[CmdletBinding()]
param(
    [switch]$KeepWorkspace,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Programs\adbgath")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$pathsToRemove = @((Join-Path $InstallRoot "bin"), (Join-Path $InstallRoot "platform-tools"))
$current = [Environment]::GetEnvironmentVariable("Path", "User")
$parts = @($current -split ';' | Where-Object { $_ -and $_.Trim() })
$filtered = $parts | Where-Object {
    $candidate = $_.TrimEnd('\')
    -not ($pathsToRemove | Where-Object { $candidate -ieq $_.TrimEnd('\') })
}
[Environment]::SetEnvironmentVariable("Path", ($filtered -join ';'), "User")

foreach ($name in @("ADB_PATH", "ADBGATH_HOME", "BUNDLETOOL_JAR")) {
    $value = [Environment]::GetEnvironmentVariable($name, "User")
    if (-not $value -or $value.StartsWith($InstallRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        [Environment]::SetEnvironmentVariable($name, $null, "User")
    }
}

if (Test-Path $InstallRoot) { Remove-Item $InstallRoot -Recurse -Force }
if (-not $KeepWorkspace) {
    $workspace = if ($env:ADBGATH_WORKSPACE) { $env:ADBGATH_WORKSPACE } else { Join-Path $HOME "adbgath-workspace" }
    if (Test-Path $workspace) { Remove-Item $workspace -Recurse -Force }
}
Write-Host "adbgath was removed. Open a new terminal to refresh PATH." -ForegroundColor Green
