[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $PSScriptRoot "..\\..\\portable-adbgath"),
    [string]$OfflineCache,
    [switch]$SkipFrida,
    [switch]$SkipBundletool,
    [switch]$Force,
    [string]$Proxy
)

$installer = Join-Path $PSScriptRoot "install.ps1"
& $installer -InstallRoot $Destination -NoPathChanges -OfflineCache $OfflineCache -SkipFrida:$SkipFrida -SkipBundletool:$SkipBundletool -Force:$Force -Proxy $Proxy
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Portable ADB-Gath is ready at $Destination\\bin\\adbgath.cmd" -ForegroundColor Green
