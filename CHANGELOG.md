# Changelog

All notable changes to ADB-Gath are documented here.

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
