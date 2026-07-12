# Windows installation and operation

## Supported hosts

- Windows 10 version 1809 or newer.
- Windows 11.
- Windows Server environments that provide Windows PowerShell and permit user-level Python installation.

The installer is designed for a standard user account. Administrator privileges are not required for the default user-scoped installation, although organization policy may restrict WinGet, Python downloads, or environment-variable changes.

## Installation flow

Run:

```bat
installers\windows\install.cmd
```

`install.cmd` delegates to the signed-script-compatible PowerShell logic in `install.ps1`. The PowerShell installer:

1. Searches for Python 3.14, 3.13, 3.12, or 3.11 through the Python launcher and standard executable names.
2. Installs Python 3.12 with WinGet when no compatible interpreter exists.
3. Falls back to the official Python 3.12.10 user installer when WinGet is unavailable or unsuccessful.
4. Creates `%LOCALAPPDATA%\Programs\adbgath\venv`.
5. Installs adbgath and its Python dependencies into that isolated environment.
6. Downloads `platform-tools-latest-windows.zip` from Google's official Android repository.
7. Verifies that the archive contains `adb.exe` before moving it into the installation root.
8. Generates command launchers under `%LOCALAPPDATA%\Programs\adbgath\bin`.
9. Adds the launcher and Platform-Tools directories to the current user's `PATH` without duplicating entries.
10. Configures `ADB_PATH` and `ADBGATH_HOME` at user scope.
11. Runs version checks for both tools.

No binaries are committed to the repository. Python-generated entry points and Android Platform-Tools are created or downloaded during installation.

## Installation paths

```text
%LOCALAPPDATA%\Programs\adbgath\
├── bin\
│   ├── adbgath.cmd
│   └── adbgath-web.cmd
├── platform-tools\
│   ├── adb.exe
│   └── ...
└── venv\
    └── Scripts\
```

Default workspace:

```text
%USERPROFILE%\adbgath-workspace
```

## Verification

Open a new Command Prompt or PowerShell window:

```bat
where adbgath
where adb
adbgath --version
adb version
adbgath doctor
```

Connect a device, unlock it, and accept the RSA authorization prompt:

```bat
adb devices -l
adbgath devices
```

## Web UI

```bat
adbgath web
```

The default browser opens at `http://127.0.0.1:8765`.

## Reinstallation and repair

Force environment recreation and Platform-Tools replacement:

```bat
installers\windows\install.cmd -Force
```

Skip optional components:

```bat
installers\windows\install.cmd -SkipFrida
installers\windows\install.cmd -SkipPlatformTools
```

`-SkipPlatformTools` is intended for systems that already provide a trusted `adb.exe` in `PATH` or through `ADB_PATH`.

## Uninstallation

```bat
installers\windows\uninstall.cmd
```

Keep reports, captures, uploads, and APK downloads:

```bat
installers\windows\uninstall.cmd -KeepWorkspace
```

## Troubleshooting

### `adbgath` is not recognized

Open a new terminal after installation. Verify that the user `PATH` contains:

```text
%LOCALAPPDATA%\Programs\adbgath\bin
```

### `adb` is not recognized

Verify:

```bat
where adb
set ADB_PATH
```

Expected Platform-Tools directory:

```text
%LOCALAPPDATA%\Programs\adbgath\platform-tools
```

### Device is unauthorized

Unlock the device and accept the RSA authorization prompt. Then run:

```bat
adb kill-server
adb start-server
adb devices -l
```

### Wireless device does not appear

Pair and connect using the host/ports displayed by Android Wireless Debugging:

```bat
adb pair 192.168.1.50:37123
adbgath connect 192.168.1.50:5555
```

### Corporate proxy or TLS inspection blocks downloads

The installer uses HTTPS endpoints from Python.org, PyPI, and Google's Android repository. Configure the organization's approved proxy and certificate trust before rerunning the installer. Do not disable TLS validation.
