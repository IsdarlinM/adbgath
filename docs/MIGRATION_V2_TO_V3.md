# Migration from 2.2.0 to 3.0.0

## Why this is a major version

Version 2.2.0 was implemented primarily in Bash and installed under Unix-specific paths. Version 3.0.0 replaces that execution core with Python to provide native Windows support, a shared web API, typed validation, structured results, and cross-platform tests.

## Preserved workflows

- Device listing and wireless connect.
- User/profile, package, and APK path listing.
- APK download, install, uninstall, and replacement.
- Device collection and information profiles.
- Logcat listening, filtering, capture, and clearing.
- Rooted network capture.
- Inventory, posture checks, package permission inspection, and reporting.
- Optional static/runtime/proxy/backup/content/Frida/MASTG-oriented workflows.

## CLI changes

The recommended v3 syntax uses subcommands:

```bash
adbgath --device SERIAL --user current install app.apk
adbgath --device SERIAL logs capture --duration 30
```

Common v2 flags remain translated when no v3 subcommand is supplied:

```bash
adbgath --device SERIAL -l packages
adbgath --device SERIAL -i network
adbgath --device SERIAL --user 0 -I app.apk
```

## Configuration changes

Shell-specific `config.sh` loading is replaced by portable environment variables and command-line options:

```text
ADB_PATH
ADBGATH_HOME
ADBGATH_WORKSPACE
```

## Installation changes

- Linux: `./installers/linux/install.sh`
- Windows: `installers\windows\install.cmd`

Both installers create isolated Python environments and global user-level launchers.
