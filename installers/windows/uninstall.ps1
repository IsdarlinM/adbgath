[CmdletBinding()]
param(
    [switch]$KeepWorkspace,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Programs\adbgath")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')

function Test-PathInsideInstallRoot {
    param([string]$Path)
    if (-not $Path) { return $false }
    try {
        $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
        if ($full.Equals($InstallRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
        $prefix = $InstallRoot + '\'
        return $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
    }
    catch {
        return $false
    }
}

function Get-AdbgathProcesses {
    $result = @()
    try {
        $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    }
    catch {
        Write-Verbose "Unable to enumerate Win32_Process through CIM: $($_.Exception.Message)"
        return @()
    }

    foreach ($process in $processes) {
        $path = [string]$process.ExecutablePath
        if ($path -and (Test-PathInsideInstallRoot $path)) {
            $result += $process
        }
    }
    return @($result)
}

function Stop-AdbgathProcesses {
    $processes = @(Get-AdbgathProcesses)
    if ($processes.Count -eq 0) { return }

    foreach ($process in $processes) {
        $path = [string]$process.ExecutablePath
        Write-Host "[adbgath] Stopping locked process $($process.Name) (PID $($process.ProcessId)) from $path"
        Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
    }

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (@(Get-AdbgathProcesses).Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    }

    $remaining = @(Get-AdbgathProcesses)
    if ($remaining.Count -gt 0) {
        $details = ($remaining | ForEach-Object { "$($_.Name) (PID $($_.ProcessId))" }) -join ', '
        throw "Unable to stop processes that are using the ADB-Gath installation: $details"
    }
}

function Clear-ReadOnlyAttributes {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }

    $items = @()
    try {
        $items += Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        $items += Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
    catch {
        return
    }

    foreach ($item in $items) {
        try {
            if (($item.Attributes -band [System.IO.FileAttributes]::ReadOnly) -ne 0) {
                $item.Attributes = $item.Attributes -band (-bnot [System.IO.FileAttributes]::ReadOnly)
            }
        }
        catch {
            Write-Verbose "Unable to clear read-only attribute from $($item.FullName): $($_.Exception.Message)"
        }
    }
}

function Remove-TreeWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Attempts = 8
    )

    if (-not (Test-Path -LiteralPath $Path)) { return }

    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        Stop-AdbgathProcesses
        Clear-ReadOnlyAttributes $Path
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        }
        catch {
            $lastError = $_
            if ($attempt -lt $Attempts) {
                Write-Host "[adbgath] Removal attempt $attempt failed; waiting for Windows to release file handles..."
                Start-Sleep -Milliseconds ([Math]::Min(2000, 250 * $attempt))
            }
        }
    }

    throw "Unable to remove '$Path' after $Attempts attempts. Last error: $($lastError.Exception.Message)"
}

# A current working directory inside the installation can keep directory handles
# alive on Windows. Move away before terminating processes and deleting the tree.
$currentDirectory = (Get-Location).Path
if (Test-PathInsideInstallRoot $currentDirectory) {
    Set-Location ([System.IO.Path]::GetTempPath())
}

# Remove the managed installation first. Environment changes are intentionally
# delayed until deletion succeeds so a failed uninstall does not leave a broken PATH.
if (Test-Path -LiteralPath $InstallRoot) {
    Write-Host "[adbgath] Removing installation from $InstallRoot"
    Remove-TreeWithRetry -Path $InstallRoot
}

$pathsToRemove = @(
    (Join-Path $InstallRoot "bin"),
    (Join-Path $InstallRoot "platform-tools")
)
$current = [Environment]::GetEnvironmentVariable("Path", "User")
$parts = if ($current) { @($current -split ';' | Where-Object { $_ -and $_.Trim() }) } else { @() }
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

if (-not $KeepWorkspace) {
    $workspace = if ($env:ADBGATH_WORKSPACE) { $env:ADBGATH_WORKSPACE } else { Join-Path $HOME "adbgath-workspace" }
    if (Test-Path -LiteralPath $workspace) {
        Remove-Item -LiteralPath $workspace -Recurse -Force -ErrorAction Stop
    }
}

Write-Host "adbgath was removed. Open a new terminal to refresh PATH." -ForegroundColor Green
