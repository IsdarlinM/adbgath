# Changelog

All notable changes to this project are documented here.

## [3.0.0] - 2026-07-11

### Added

- Native Windows and Linux Python core.
- Global `adbgath` and `adbgath-web` entry points.
- Professional local web workspace with full allowlisted CLI capability coverage.
- Live WebSocket logcat viewer.
- Secure local upload staging and workspace-confined artifact downloads.
- Windows CMD/PowerShell installer that provisions Python, Platform-Tools, Python dependencies, launchers, and user environment variables.
- Linux dependency-aware installer.
- Shared ADB subprocess wrapper with input validation, timeouts, structured results, and no shell execution.
- Package inventory, app summary, runtime inspection, static APK metadata/hash checks, proxy controls, forwarding, backups, content providers, optional Frida support, security reports, and MASTG-oriented evidence collection.
- Windows/Ubuntu CI matrix and fake-ADB test coverage.

### Changed

- Replaced the Linux-only Bash architecture with a cross-platform service layer.
- Standardized documentation and command help in English.
- Moved generated evidence into a configurable workspace.

### Security

- Added loopback-only web defaults, session cookies, trusted hosts, restrictive browser headers, an action allowlist, destructive-action confirmation, upload limits, and artifact path confinement.
