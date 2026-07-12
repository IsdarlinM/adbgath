# Migration from 2.2.0 to 3.2.9

## Summary

ADB-Gath 2.2.0 relied primarily on Bash modules and Unix installation paths. Version 3.2.9 replaces that execution core with a cross-platform Python architecture while preserving common legacy options and the historical ADB-Gath branding.

## Preserved workflows

- Device discovery and wireless connection.
- Android user/profile handling.
- Package and APK-path listing.
- APK download, installation, uninstallation, and replacement.
- Device information and collection profiles.
- Logcat listening, filtering, capture, and clearing.
- Rooted packet capture.
- Batch input with `-f/--file`.
- Common legacy options such as `-l`, `-i`, `-I`, `-U`, `-R`, and `-C`.

## New architecture

Recommended syntax uses subcommands:

```bash
adbgath --device SERIAL --user current install app.apk
adbgath --device SERIAL logs capture --duration 30
```

The CLI, interactive mode, and web UI share one service layer. There is no separate Windows implementation and no browser shell.

## Important behavior changes

### Explicit target and profile

Installing, uninstalling, replacing, or modifying application state requires an explicit device and Android user/profile:

```bash
adbgath --device SERIAL --user 0 install app.apk
```

This prevents an operation from silently targeting the wrong device or work profile.

### Transactional replacement

`replace` now attempts in-place replacement first. It does not uninstall unless `--allow-uninstall` is supplied. When fallback installation fails, the command attempts to reinstall the previously pulled APK set.

### Configuration

Portable environment variables replace shell-specific configuration loading:

```text
ADB_PATH
ADBGATH_HOME
ADBGATH_WORKSPACE
BUNDLETOOL_JAR
ADBGATH_MANIFEST_HMAC_KEY
```

### Persistent data

Projects, sessions, findings, jobs, snapshots, groups, and artifact metadata are stored in `adbgath.db` inside the workspace. Existing downloaded artifacts remain regular files.

## New high-level commands

```text
capabilities
install-set
bundle
evidence
assess
snapshot
project
findings
group
run-group
plugin
report
update
doctor --fix
web
```

Use `adbgath COMMAND -h` for complete arguments.
