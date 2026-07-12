[CmdletBinding()]
param(
    [switch]$SkipPlatformTools,
    [switch]$SkipFrida,
    [switch]$SkipBundletool,
    [switch]$Force,
    [switch]$Repair,
    [switch]$NoPathChanges,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Programs\adbgath"),
    [string]$OfflineCache,
    [string]$Proxy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ($OfflineCache) { $OfflineCache = [System.IO.Path]::GetFullPath($OfflineCache) }

function Write-Step([string]$Message) {
    Write-Host "[adbgath] $Message" -ForegroundColor Cyan
}

function Get-VerifiedDownload([string]$Uri, [string]$Destination, [string]$OfflineName = "") {
    if ($OfflineCache) {
        $name = if ($OfflineName) { $OfflineName } else { Split-Path $Destination -Leaf }
        $cached = Join-Path $OfflineCache $name
        if (-not (Test-Path $cached)) { throw "Offline dependency not found: $cached" }
        Copy-Item $cached $Destination -Force
        return
    }
    $arguments = @{ Uri = $Uri; OutFile = $Destination; UseBasicParsing = $true }
    if ($Proxy) { $arguments.Proxy = $Proxy }
    Invoke-WebRequest @arguments
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
    $winget = if ($OfflineCache) { $null } else { Get-Command winget.exe -ErrorAction SilentlyContinue }
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
    Write-Step "Obtaining the official Python installer."
    Get-VerifiedDownload $installerUrl $installer (Split-Path $installer -Leaf)
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
    Write-Step "Obtaining Android SDK Platform-Tools from Google or the offline cache."
    Get-VerifiedDownload "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" $zip "platform-tools-latest-windows.zip"
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

function Ensure-Java {
    $java = Get-Command java.exe -ErrorAction SilentlyContinue
    if ($java) { return $java.Source }
    if ($OfflineCache) {
        Write-Warning "Java is not present. Place a supported Java runtime on PATH before using bundletool."
        return $null
    }
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Step "Installing Microsoft OpenJDK 21 for bundletool."
        & $winget.Source install --exact --id Microsoft.OpenJDK.21 --scope user --silent --accept-package-agreements --accept-source-agreements
        $java = Get-Command java.exe -ErrorAction SilentlyContinue
        if ($java) { return $java.Source }
    }
    Write-Warning "Java could not be installed automatically. bundletool will remain optional until Java is available."
    return $null
}

function Install-Bundletool([string]$Root) {
    $tools = Join-Path $Root "tools"
    New-Item -ItemType Directory -Path $tools -Force | Out-Null
    $jar = Join-Path $tools "bundletool.jar"
    if ((Test-Path $jar) -and -not $Force) { return $jar }
    if ($OfflineCache) {
        $cachedJar = Join-Path $OfflineCache "bundletool.jar"
        $cachedHash = Join-Path $OfflineCache "bundletool.jar.sha256"
        if (-not (Test-Path $cachedJar) -or -not (Test-Path $cachedHash)) {
            throw "Offline bundletool requires bundletool.jar and bundletool.jar.sha256."
        }
        Copy-Item $cachedJar $jar -Force
        $expected = ((Get-Content $cachedHash -Raw).Trim() -split '\s+')[0]
        $actual = (Get-FileHash $jar -Algorithm SHA256).Hash
        if ($actual -ine $expected) { Remove-Item $jar -Force; throw "Offline bundletool checksum verification failed." }
        return $jar
    }
    Write-Step "Resolving the latest official Google bundletool release."
    $headers = @{ "User-Agent" = "ADB-Gath-Installer"; "Accept" = "application/vnd.github+json" }
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/google/bundletool/releases/latest" -Headers $headers
    $asset = $release.assets | Where-Object { $_.name -match '^bundletool-all-.*\.jar$' } | Select-Object -First 1
    if (-not $asset) { throw "The official bundletool release did not contain the expected JAR." }
    if ($asset.browser_download_url -notmatch '^https://github.com/google/bundletool/releases/download/') {
        throw "Unexpected bundletool download origin."
    }
    Get-VerifiedDownload $asset.browser_download_url $jar $asset.name
    $actual = (Get-FileHash $jar -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($asset.digest -and $asset.digest -match '^sha256:(.+)$' -and $actual -ne $Matches[1].ToLowerInvariant()) {
        Remove-Item $jar -Force
        throw "Official bundletool release digest verification failed."
    }
    Set-Content -Path "$jar.sha256" -Value "$actual  bundletool.jar" -Encoding ASCII
    return $jar
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$VenvRoot = Join-Path $InstallRoot "venv"
$BinRoot = Join-Path $InstallRoot "bin"

Write-Step "Installing from $ProjectRoot"
New-Item -ItemType Directory -Path $InstallRoot, $BinRoot -Force | Out-Null

$python = Resolve-Python
if (-not $python) { $python = Install-Python }
Write-Step "Using Python: $($python.Exe) $($python.Args -join ' ')"

if ((Test-Path $VenvRoot) -and $Force -and -not $Repair) { Remove-Item $VenvRoot -Recurse -Force }
if (-not (Test-Path (Join-Path $VenvRoot "Scripts\python.exe"))) {
    Write-Step "Creating an isolated Python environment."
    $venvArgs = @($python.Args) + @("-m", "venv", $VenvRoot)
    & $python.Exe @venvArgs
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the Python virtual environment." }
}

$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
Write-Step "Installing adbgath and web dependencies."
$PipSourceArgs = @()
if ($OfflineCache) { $PipSourceArgs = @("--no-index", "--find-links", $OfflineCache) }
if (-not $OfflineCache) {
    & $VenvPython -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "Unable to update Python packaging tools." }
}
& $VenvPython -m pip install --disable-pip-version-check @PipSourceArgs --upgrade $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Unable to install adbgath Python dependencies." }
if (-not $SkipFrida) {
    Write-Step "Installing optional Frida command-line tools."
    & $VenvPython -m pip install --disable-pip-version-check @PipSourceArgs --upgrade "frida-tools>=13"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Frida tools could not be installed. Core CLI and web features remain available; rerun with a compatible Python version to enable Frida."
    }
}

$PlatformRoot = $null
$BundletoolJar = $null
if (-not $SkipPlatformTools) {
    $PlatformRoot = Install-PlatformTools $InstallRoot
    if (-not $NoPathChanges) { Add-UserPath $PlatformRoot }
    if (-not $NoPathChanges) { [Environment]::SetEnvironmentVariable("ADB_PATH", (Join-Path $PlatformRoot "adb.exe"), "User") }
    $env:ADB_PATH = Join-Path $PlatformRoot "adb.exe"
}

if (-not $SkipBundletool) {
    try {
        $JavaExe = Ensure-Java
        $BundletoolJar = Install-Bundletool $InstallRoot
        if (-not $NoPathChanges) { [Environment]::SetEnvironmentVariable("BUNDLETOOL_JAR", $BundletoolJar, "User") }
        $env:BUNDLETOOL_JAR = $BundletoolJar
    } catch {
        Write-Warning "bundletool could not be installed securely: $($_.Exception.Message)"
    }
}

$AdbgathExe = Join-Path $VenvRoot "Scripts\adbgath.exe"
$WebExe = Join-Path $VenvRoot "Scripts\adbgath-web.exe"
$AdbCmd = if ($PlatformRoot) { 'set "ADB_PATH=' + (Join-Path $PlatformRoot "adb.exe") + '"' } else { "rem ADB_PATH inherited from environment" }
$BundleCmd = if ($BundletoolJar) { 'set "BUNDLETOOL_JAR=' + $BundletoolJar + '"' } else { "rem BUNDLETOOL_JAR inherited from environment" }
@"
@echo off
set "ADBGATH_HOME=$InstallRoot"
$AdbCmd
$BundleCmd
"$AdbgathExe" %*
"@ | Set-Content -Path (Join-Path $BinRoot "adbgath.cmd") -Encoding ASCII
@"
@echo off
set "ADBGATH_HOME=$InstallRoot"
$AdbCmd
$BundleCmd
"$WebExe" %*
"@ | Set-Content -Path (Join-Path $BinRoot "adbgath-web.cmd") -Encoding ASCII

if (-not $NoPathChanges) { Add-UserPath $BinRoot }
if (-not $NoPathChanges) { [Environment]::SetEnvironmentVariable("ADBGATH_HOME", $InstallRoot, "User") }
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
if ($NoPathChanges) {
    Write-Host "Portable/no-PATH mode: run $BinRoot\adbgath.cmd"
} else {
    Write-Host "A new terminal will inherit the updated user PATH automatically."
}
