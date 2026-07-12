# Windows and Web Modernization Report

## Original limitation

The 2.2.0 implementation was centered on Bash modules and Unix installation paths. That made the application dependent on a POSIX shell, Unix filesystem conventions, and Linux-oriented dependency handling. A Windows wrapper around the existing shell scripts would not have produced reliable native behavior.

## Architecture selected

Version 3.0.0 uses a shared Python service layer:

```text
Windows CLI ───────┐
Linux CLI ─────────┼── AdbgathService ── AdbClient ── adb / adb.exe
Local Web UI ──────┘
```

This design gives Windows and Linux the same validation, timeouts, error handling, output format, report paths, and security controls. It also prevents the web interface from becoming a second, inconsistent implementation.

## Windows work completed

- Replaced Bash-only operational logic with Python 3.11+.
- Added native console entry points: `adbgath` and `adbgath-web`.
- Added CMD launchers backed by an isolated user-scoped virtual environment.
- Added Python detection and user-scoped installation through WinGet with a signed official-installer fallback.
- Added Android SDK Platform-Tools download and `adb.exe` validation.
- Added persistent user `PATH`, `ADB_PATH`, and `ADBGATH_HOME` configuration.
- Added repair, optional-component, and uninstall flows.
- Added Windows/Ubuntu CI coverage for Python 3.11, 3.12, and 3.13.

## CLI compatibility

The cross-platform CLI supports the original primary workflows:

- Device discovery and wireless connection.
- Android users/profiles.
- Package and APK-path listing.
- APK download, installation, uninstallation, and replacement.
- UTF-8 batch files through `-f/--file`.
- Basic/system/network/security device information.
- Logcat listening, filtering, capture, and clearing.
- Rooted tcpdump upload and capture.
- Evidence collection.
- Interactive mode when no command is supplied.
- Common v2 short-flag translation.

The v3 CLI additionally exposes structured JSON output, app permission summaries, runtime inspection, proxy and port mappings, app backup, content-provider discovery, optional Frida operations, local static APK checks, security reports, inventory, diagnostics, and MASTG-oriented evidence bundles.

## Web interface

The local web workspace includes:

- Responsive dark security-dashboard design.
- Device and Android-profile selection.
- Complete allowlisted operation builder.
- Package inventory and APK-path display.
- Secure upload staging for APKs, Frida scripts, and tcpdump tools.
- Live WebSocket logcat.
- Timed log capture and filtering.
- Security severity summary and findings.
- Collection and MASTG evidence workflows.
- Workspace artifact listing and downloads.
- Environment diagnostics.

## Security decisions

- No `shell=True` host execution.
- No arbitrary terminal or raw-command web endpoint.
- Typed/allowlisted web actions.
- Input validation for devices, packages, users, paths, ports, interfaces, and durations.
- Explicit device and user selection for app-changing operations.
- Literal `AUTHORIZED` confirmation for destructive web actions.
- Loopback-only web binding.
- HttpOnly/SameSite session cookie and restrictive browser headers.
- Upload limit and normalized filenames.
- Workspace path confinement for downloads.
- Subprocess timeouts and structured errors.

## Validation completed

- Ruff static checks.
- Python compilation checks.
- JavaScript syntax validation.
- Bash syntax validation for Linux launchers/installers.
- 33 automated tests with fake ADB behavior.
- Frontend/backend web-action parity test.
- Installer-content and no-committed-binary checks.
- Python wheel and source-distribution build.
- Clean virtual-environment installation from the built wheel.
- Real local Uvicorn smoke test with a simulated ADB executable, including bootstrap API and static security headers.

## Validation boundary

The Windows installer and Windows CI workflow are included, but this delivery environment is Linux. The installer was therefore reviewed and tested statically here rather than executed against a physical Windows host. The included GitHub Actions matrix is designed to perform that native Windows validation on every push and pull request.
