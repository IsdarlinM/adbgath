# Windows installation and operation

## Default installation

Run from Command Prompt or Windows Terminal:

```bat
installers\windows\install.cmd
```

Default root:

```text
%LOCALAPPDATA%\Programs\adbgath\
```

The installer:

1. Locates Python 3.11+ through the Python launcher, executable names, and common installation roots.
2. Uses WinGet to install Python 3.12 when available.
3. Falls back to an official Python installer and verifies its Authenticode signer.
4. Creates an isolated virtual environment.
5. Installs ADB-Gath and web dependencies.
6. Optionally installs Frida tools.
7. Downloads Android SDK Platform-Tools and validates `adb.exe` presence.
8. Optionally installs Java and official Google bundletool.
9. Generates `adbgath.cmd` and `adbgath-web.cmd`.
10. Adds launcher and Platform-Tools directories to the user `PATH`.
11. Configures `ADB_PATH`, `ADBGATH_HOME`, and `BUNDLETOOL_JAR`.
12. Runs CLI and ADB validation.

No prebuilt binaries are stored in the repository.

## Options

```bat
installers\windows\install.cmd -Repair
installers\windows\install.cmd -Force
installers\windows\install.cmd -SkipPlatformTools
installers\windows\install.cmd -SkipFrida
installers\windows\install.cmd -SkipBundletool
installers\windows\install.cmd -InstallRoot "D:\Tools\adbgath"
installers\windows\install.cmd -Proxy "http://proxy.example:8080"
installers\windows\install.cmd -OfflineCache "D:\adbgath-cache"
```

`-Repair` preserves the existing virtual environment while reinstalling/upgrading files and regenerating launchers. `-Force` recreates the environment.

## Portable mode

```bat
installers\windows\portable.cmd
```

The portable installer uses `-NoPathChanges` and creates launchers inside the destination. It does not persist user environment variables.

```bat
portable-adbgath\bin\adbgath.cmd doctor
```

## Offline cache

An offline cache should contain:

- Wheels required by ADB-Gath and optional Frida when not skipped.
- `platform-tools-latest-windows.zip` when Platform-Tools are required.
- `bundletool.jar` and `bundletool.jar.sha256` when bundletool is required.
- The official Python installer when Python is not already installed.

See `OFFLINE_INSTALL.md`.

## Driver diagnostics

```bat
adbgath doctor
```

The doctor reports PowerShell, ADB path conflicts, architecture, free workspace space, optional Android tools, environment variables, and connected Android/ADB driver entries visible through `pnputil`.

Driver installation remains vendor/device-specific. Install the OEM USB driver or Google USB driver appropriate for the authorized device when Windows does not enumerate the ADB interface.

## Uninstall

```bat
installers\windows\uninstall.cmd
```

Preserve the default workspace:

```bat
installers\windows\uninstall.cmd -KeepWorkspace
```

For a custom installation root:

```bat
installers\windows\uninstall.cmd -InstallRoot "D:\Tools\adbgath" -KeepWorkspace
```
