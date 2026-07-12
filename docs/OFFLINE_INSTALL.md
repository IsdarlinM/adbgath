# Offline and portable installation

## Security model

Offline mode never attempts to resolve Python packages from the Internet. The operator supplies a trusted cache. Build the cache on a connected machine, transfer it through an approved process, and verify its hashes before installation.

## Python wheel cache

From a connected system with a compatible Python/platform target:

```bash
python -m pip download -d adbgath-cache .
python -m pip download -d adbgath-cache "frida-tools>=13"
```

For a target platform different from the download host, use a dedicated build machine or carefully selected pip platform/ABI options.

## Windows cache additions

Add as needed:

```text
platform-tools-latest-windows.zip
bundletool.jar
bundletool.jar.sha256
python-3.12.10-amd64.exe or python-3.12.10-arm64.exe
```

Run:

```bat
installers\windows\install.cmd -OfflineCache "D:\adbgath-cache"
```

Skip optional components whose dependencies are not present:

```bat
installers\windows\install.cmd -OfflineCache "D:\adbgath-cache" -SkipFrida -SkipBundletool
```

## Linux cache additions

Add:

```text
bundletool.jar
bundletool.jar.sha256
```

Python 3.11+, venv support, ADB, and Java must already be installed through the offline operating-system package process.

```bash
./installers/linux/install.sh --offline-cache /media/adbgath-cache
```

## Portable mode

Windows:

```bat
installers\windows\portable.cmd
```

Linux:

```bash
./installers/linux/portable.sh ./portable-adbgath
```

Portable mode does not add persistent `PATH` or user environment entries. It still creates a Python virtual environment and may download dependencies unless an offline cache is supplied.
