[CmdletBinding()]
param(
    [switch]$SkipPlatformTools,
    [switch]$SkipFrida,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step([string]$Message) {
    Write-Host "[adbgath] $Message" -ForegroundColor Cyan
}

function Test-Python311([string]$Executable, [string[]]$PrefixArgs = @()) {
    try {
        $script = "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        & $Executable @PrefixArgs -c $script 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Resolve-Python {
    $candidates = @()
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($version in @("-3.14", "-3.13", "-3.12", "-3.11")) {
            $candidates += [pscustomobject]@{ Exe = $py.Source; Args = [string[]]@($version) }
        }
    }
    foreach ($name in @("python.exe", "python3.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += [pscustomobject]@{ Exe = $command.Source; Args = [string[]]@() }
        }
    }
    $pythonRoots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        (Join-Path $env:ProgramFiles "Python")
    )
    foreach ($root in $pythonRoots) {
        if (Test-Path $root) {
            Get-ChildItem $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending |
                ForEach-Object {
                    $candidates += [pscustomobject]@{ Exe = $_.FullName; Args = [string[]]@() }
                }
        }
    }
    foreach ($candidate in $candidates) {
        if (Test-Python311 $candidate.Exe $candidate.Args) {
            return @{ Exe = $candidate.Exe; Args = [string[]]$candidate.Args }
        }
    }
    return $null
}

function Install-Python {
    Write-Step "Python 3.11+ was not found. Installing Python 3.12 for the current user."
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        & $winget.Source install --exact --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Write-Warning "WinGet Python installation returned $LASTEXITCODE; trying the official installer." }
    }
    $resolved = Resolve-Python
    if ($resolved) { return $resolved }

    $architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    $installerArch = if ($architecture -eq "Arm64") { "arm64" } elseif ($architecture -eq "X64") { "amd64" } else {
        throw "Unsupported Windows architecture: $architecture. Use a supported x64 or ARM64 Python installation."
    }
    $installerUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-$installerArch.exe"
    $installer = Join-Path $env:TEMP "python-3.12.10-$installerArch.exe"
    Write-Step "Downloading the official Python installer."
    Invoke-WebRequest -Uri $installerUrl -OutFile $installer -UseBasicParsing
    $signature = Get-AuthenticodeSignature -FilePath $installer
    if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch "Python Software Foundation") {
        Remove-Item $installer -Force -ErrorAction SilentlyContinue
        throw "The downloaded Python installer did not have a valid Python Software Foundation signature."
    }
    $process = Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1" -Wait -PassThru
    Remove-Item $installer -Force -ErrorAction SilentlyContinue
    if ($process.ExitCode -ne 0) { throw "Python installer failed with exit code $($process.ExitCode)." }

    $pythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    $possible = Get-ChildItem $pythonRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($possible -and (Test-Python311 $possible.FullName @())) {
        return @{ Exe = $possible.FullName; Args = [string[]]@() }
    }
    throw "Python 3.11+ could not be installed or located."
}

function Add-UserPath([string]$Directory) {
    $full = [System.IO.Path]::GetFullPath($Directory).TrimEnd('\')
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($current -split ';' | Where-Object { $_ -and $_.Trim() })
    if (-not ($parts | Where-Object { $_.TrimEnd('\') -ieq $full })) {
        $newPath = (($parts + $full) -join ';')
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    }
    if (-not (($env:Path -split ';') | Where-Object { $_.TrimEnd('\') -ieq $full })) {
        $env:Path = "$full;$env:Path"
    }
}

function Install-PlatformTools([string]$InstallRoot) {
    $platformRoot = Join-Path $InstallRoot "platform-tools"
    $adb = Join-Path $platformRoot "adb.exe"
    if ((Test-Path $adb) -and -not $Force) {
        Write-Step "Android SDK Platform-Tools already exists."
        return $platformRoot
    }
    $zip = Join-Path $env:TEMP "platform-tools-latest-windows.zip"
    $extractRoot = Join-Path $env:TEMP ("adbgath-platform-tools-" + [Guid]::NewGuid().ToString("N"))
    Write-Step "Downloading Android SDK Platform-Tools from Google."
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $zip -UseBasicParsing
    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    Expand-Archive -Path $zip -DestinationPath $extractRoot -Force
    $source = Join-Path $extractRoot "platform-tools"
    if (-not (Test-Path (Join-Path $source "adb.exe"))) { throw "Downloaded Platform-Tools archive did not contain adb.exe." }
    if (Test-Path $platformRoot) { Remove-Item $platformRoot -Recurse -Force }
    Move-Item $source $platformRoot
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Remove-Item $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
    return $platformRoot
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\adbgath"
$VenvRoot = Join-Path $InstallRoot "venv"
$BinRoot = Join-Path $InstallRoot "bin"

Write-Step "Installing from $ProjectRoot"
New-Item -ItemType Directory -Path $InstallRoot, $BinRoot -Force | Out-Null

$python = Resolve-Python
if (-not $python) { $python = Install-Python }
Write-Step "Using Python: $($python.Exe) $($python.Args -join ' ')"

if ((Test-Path $VenvRoot) -and $Force) { Remove-Item $VenvRoot -Recurse -Force }
if (-not (Test-Path (Join-Path $VenvRoot "Scripts\python.exe"))) {
    Write-Step "Creating an isolated Python environment."
    $venvArgs = @($python.Args) + @("-m", "venv", $VenvRoot)
    & $python.Exe @venvArgs
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the Python virtual environment." }
}

$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
Write-Step "Installing adbgath and web dependencies."
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "Unable to update Python packaging tools." }
& $VenvPython -m pip install --disable-pip-version-check --upgrade $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Unable to install adbgath Python dependencies." }
if (-not $SkipFrida) {
    Write-Step "Installing optional Frida command-line tools."
    & $VenvPython -m pip install --disable-pip-version-check --upgrade "frida-tools>=13"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Frida tools could not be installed. Core CLI and web features remain available; rerun with a compatible Python version to enable Frida."
    }
}

$PlatformRoot = $null
if (-not $SkipPlatformTools) {
    $PlatformRoot = Install-PlatformTools $InstallRoot
    Add-UserPath $PlatformRoot
    [Environment]::SetEnvironmentVariable("ADB_PATH", (Join-Path $PlatformRoot "adb.exe"), "User")
    $env:ADB_PATH = Join-Path $PlatformRoot "adb.exe"
}

$AdbgathExe = Join-Path $VenvRoot "Scripts\adbgath.exe"
$WebExe = Join-Path $VenvRoot "Scripts\adbgath-web.exe"
@"
@echo off
"$AdbgathExe" %*
"@ | Set-Content -Path (Join-Path $BinRoot "adbgath.cmd") -Encoding ASCII
@"
@echo off
"$WebExe" %*
"@ | Set-Content -Path (Join-Path $BinRoot "adbgath-web.cmd") -Encoding ASCII

Add-UserPath $BinRoot
[Environment]::SetEnvironmentVariable("ADBGATH_HOME", $InstallRoot, "User")
$env:ADBGATH_HOME = $InstallRoot

Write-Step "Validating the installed commands."
& $AdbgathExe --version
if ($LASTEXITCODE -ne 0) { throw "adbgath command validation failed." }
if ($PlatformRoot) {
    & (Join-Path $PlatformRoot "adb.exe") version
    if ($LASTEXITCODE -ne 0) { throw "ADB validation failed." }
}

Write-Host ""
Write-Host "adbgath installation completed." -ForegroundColor Green
Write-Host "Install root : $InstallRoot"
Write-Host "CLI          : adbgath"
Write-Host "Web UI       : adbgath web"
Write-Host "Validation   : adbgath doctor"
Write-Host "A new terminal will inherit the updated user PATH automatically."
