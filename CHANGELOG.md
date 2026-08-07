# Changelog

All notable changes to ADB-Gath are documented here.

## [3.6.0] - 2026-08-07

### Added

- Bounded asynchronous process supervisor with cancellation, timeout, output backpressure, and process-tree cleanup.
- SHA-256 content-addressed artifact store with deduplication, compression, verification, migration, materialization, and garbage collection.
- RBAC policy engine with viewer, analyst, operator, and administrator roles plus explicit approval for destructive remote jobs.
- Tamper-evident hash-chained audit events.
- Optional distributed mobile-security lab controller protected by mutual TLS and per-agent tokens.
- Outbound-only Windows/Linux lab agents with operation allowlists and no arbitrary shell endpoint.
- Local PKI tooling, agent enrollment, device pools, job queueing, heartbeat/capability reporting, and result collection.
- Ed25519 plugin signing/verification and CycloneDX/SPDX SBOM generation.
- Static/runtime evidence correlation command.
- Distributed Lab Web UI for agents, jobs, policy checks, artifact integrity, and audit verification.
- SQLite schema migration 360 for lab, policy, audit, and content-addressed artifact metadata.

### Security

- Remote controller transport requires mTLS; agent URLs must use HTTPS.
- Agent authentication combines trusted client certificates with one-time enrollment tokens stored only as SHA-256 hashes on the controller.
- Remote jobs are re-authorized by policy immediately before delivery to the agent.
- Destructive remote operations require explicit approval and suitable RBAC role.
- Private PKI/signing keys are written with restrictive file permissions where supported.
- Agent tokens and private keys are excluded from audit events and normal listing APIs.

### Validation

- Added real loopback mTLS controller↔agent integration testing.
- Added 3.6 tests for CAS deduplication/integrity, RBAC, audit tamper detection, Ed25519 signing, PKI, distributed jobs, async timeout handling, SBOM generation, and Web UI APIs.

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
