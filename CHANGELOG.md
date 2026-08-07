# Changelog

All notable changes to ADB-Gath are documented here.

## [3.4.0] - 2026-08-06

### Added

- One-time Android Wireless Debugging QR pairing compatible with the AOSP `WIFI:T:ADB` payload and `studio-*` mDNS instance convention.
- Secure CLI QR workflow with expiration, optional browser opening, optional auto-connect, cancellation, and default SVG deletion.
- Professional Web QR workflow with no-store SVG delivery, countdown, live WebSocket status, cancellation, and automatic connection.
- Shared ADB/mDNS event broker with bounded event history, ordered sequence numbers, device/service change events, and adaptive failure backoff.
- Formal SQLite schema migrations with checksums, `PRAGMA user_version`, integrity validation, bounded pre-migration backups, and restoration on failure.
- Incremental inventory capture, stable content digests, list/diff/watch commands, retention limits, and database-backed history.
- Capability cache keyed by device and build fingerprint with explicit refresh support.
- `adbgath schema` and Web `schema_status` operations.

### Changed

- Wireless WebSocket clients consume one shared broker instead of performing independent mDNS polling.
- Capability cache metadata is deterministic so repeated snapshots do not produce false differences.
- Inventory digests and comparisons ignore volatile capture timestamps.
- FastAPI startup/shutdown management now uses the lifespan API.

### Security

- QR secrets are generated with `secrets`, held only in memory, sent to ADB through standard input, and excluded from process arguments, JSON, SQLite, jobs, metrics, reports, presets, and logs.
- QR SVG responses are same-origin, session-protected, CSP-constrained, and marked `Cache-Control: no-store`.
- QR creation requires explicit authorized-target confirmation and cannot be queued as a persistent background job.

## [3.3.0] - 2026-08-06

### Added

- Complete Android 11+ Wireless Debugging workflow using the six-digit pairing code shown by Android.
- `adbgath wireless` commands for status, discovery, pairing, connect, disconnect, watch, diagnostics, repair, auto-connect, known targets, aliases, local forget, and legacy TCP/IP mode.
- Detailed and legacy ADB mDNS parsers for `_adb-tls-pairing._tcp`, `_adb-tls-connect._tcp`, IPv4, IPv6, `.local` hostnames, device metadata, and ADB Wi-Fi 2.0 service versions.
- Dedicated professional Wireless Debugging Web UI with secure pairing form, live WebSocket discovery, diagnostics, known targets, aliases, and connection controls.
- Persistent non-secret wireless target inventory and local ADB execution performance metrics.
- Cancellable ADB subprocess execution for background Web UI jobs.
- Fast, detailed, and watch modes for device enumeration with concurrent root probes and short-lived caching.

### Fixed

- ADB networking commands that return exit code `0` while printing `failed to connect`, `cannot connect`, or similar errors are now reported with `ok: false`.
- Pairing codes are passed only through standard input and are excluded from command arguments, metadata, presets, jobs, reports, and persistent storage.
- Wireless capability detection now separates host mDNS state from device capabilities and checks `adb server-status`.
- Host/port validation now supports canonical IPv4, bracketed IPv6, DNS names, and `.local` hostnames.

### Security

- Web pairing requires explicit authorized-target confirmation.
- Pairing actions cannot be queued as persistent jobs.
- Wireless repair is explicit, scoped to ADB-Gath's environment file, and restarts only the local ADB server.

## [3.2.9] - 2026-07-12

### Added

- Native cross-platform Python core for Windows and Linux.
- Professional web assessment workspace with catalog-generated forms.
- Persistent projects, sessions, findings, artifacts, jobs, snapshots, and device groups.
- Transactional APK replacement with backup, explicit fallback, and rollback.
- Split APK, `.apks`, and optional AAB/bundletool workflows.
- Android manifest, component, permission, deep-link, signing, native-library, endpoint, WebView, and configuration analysis.
- Reproducible `assess` and `evidence` workflows.
- SHA-256 evidence manifests, redacted copies, and optional HMAC signatures.
- JSON, Markdown, HTML, CSV, SARIF, and PDF reports.
- Multi-device read-only group execution.
- Permission-declaring plugin interface.
- Observation-only Frida scripts for TLS, cryptography, and WebView monitoring, including version metadata, syntax validation, redacted session logs, and history.
- Secure local update, staging, smoke testing, rollback, and preservation of persistent data.
- Windows and Linux repair, portable, proxy, offline-cache, and optional-component installation modes.
- Optional authenticated TLS-only remote web mode.
- Expanded cross-platform automated test and package validation coverage.
- Workspace-confined project ZIP exports with fresh hashes and export manifests.
- Web presets, package pagination/sorting, multi-file staging, bounded logcat rendering, bookmarks, export, and severity charts.
- Dedicated native Windows-installer and Android-emulator CI workflows.

### Changed

- Version unified as `3.2.9` across source, package metadata, web UI, documentation, and reports.
- CLI and web UI now consume one shared operation catalog.
- Application-changing commands require explicit device/profile selection.
- Web operations reject undeclared fields and require confirmation for destructive actions.
- Security audit now emits PDF in addition to JSON, Markdown, HTML, and SARIF.

### Security

- Restored and regression-protected the owner-approved ADB-Gath branding.
- Removed browser-accessible arbitrary command execution paths.
- Added remote-mode TLS/token requirements, login throttling, secure cookies, HSTS, WebSocket Origin checks, and generic server errors.
- Added archive traversal, symlink, entry-count, size, and checksum controls to updates.
- Added plugin permission approval and evidence redaction.

## [2.2.0]

- Previous Bash-oriented implementation.
