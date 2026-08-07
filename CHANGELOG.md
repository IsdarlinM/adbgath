# Changelog

All notable changes to ADB-Gath are documented here.

## [3.3.0] - 2026-08-06

### Added

- Complete Android 11+ Wireless Debugging workflow using the six-digit pairing code shown by Android.
- `adbgath pair` and `adbgath wireless` commands for discovery, pairing, connect, disconnect, status, watch, diagnostics, safe repair, auto-connect, known targets, aliases, local forget and legacy TCP/IP mode.
- Detailed and legacy ADB mDNS parsers for `_adb-tls-pairing._tcp`, `_adb-tls-connect._tcp`, IPv4, bracketed IPv6, `.local` hostnames and ADB Wi-Fi metadata.
- Dedicated professional Wireless Debugging Web UI with secure pairing form, live WebSocket discovery, diagnostics, known targets, aliases and connection controls.
- Persistent non-secret wireless target inventory and local ADB execution-performance metrics.
- Cooperative cancellation for background ADB subprocesses.
- Fast, detailed and watch modes for device enumeration with concurrent root probes and short-lived caching.

### Fixed

- ADB networking commands that return exit code `0` while printing `failed to connect`, `cannot connect`, Windows error `10061` or equivalent failures are now reported with `ok: false`.
- Pairing codes are passed only through standard input and are excluded from command arguments, metadata, presets, jobs, reports, logs, metrics and persistent storage.
- Wireless capability detection now separates host mDNS state from device capabilities and checks `adb server-status`.
- Host/port validation now supports canonical IPv4, bracketed IPv6, DNS names and `.local` hostnames.

### Security

- Web pairing requires explicit authorized-target confirmation.
- Pairing actions cannot be queued as persistent jobs.
- Wireless repair is explicit, scoped to ADB-Gath's environment file and restarts only the local ADB server.
- Discovery is limited to ADB's advertised mDNS services; no IP-range scanning, port brute forcing or pairing-code guessing was added.

## [3.2.9] - 2026-07-12

### Added

- Native cross-platform Python core for Windows and Linux.
- Professional web assessment workspace with catalog-generated forms.
- Persistent projects, sessions, findings, artifacts, jobs, snapshots and device groups.
- Transactional APK replacement with backup, explicit fallback and rollback.
- Split APK, `.apks` and optional AAB/bundletool workflows.
- Android manifest, component, permission, deep-link, signing, native-library, endpoint, WebView and configuration analysis.
- Reproducible assessment and evidence workflows with SHA-256 manifests and redaction.
- JSON, Markdown, HTML, CSV, SARIF and PDF reports.
- Multi-device read-only group execution, plugins, controlled Frida observation and secure update rollback.
- Windows/Linux installation, repair, portable and offline-cache workflows.

### Security

- Restored and regression-protected the owner-approved ADB-Gath branding.
- Removed browser-accessible arbitrary command execution paths.
- Added TLS/token requirements for optional non-loopback web mode.

## [2.2.0]

- Previous Bash-oriented implementation.
