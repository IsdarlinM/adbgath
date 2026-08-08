# Changelog

All notable changes to ADB-Gath are documented here.

## [3.7.1] - 2026-08-08

### Added

- A themed ADB-Gath `<dialog>` workflow for saving/replacing Command Center presets instead of using the browser's native prompt UI.
- Server-side preset storage scoped to the authenticated Web user and active workspace.
- Themed confirmation dialogs for deleting presets, cancelling background jobs, and clearing the device log buffer.
- Inline Command Center validation with focus/scroll to the first invalid field.
- Busy/disabled states for operation execution, Security Audit, MASTG bundle generation, and package loading.
- Copy-to-clipboard controls for structured output consoles.
- ARIA live-region behavior for Web notifications and keyboard-compatible dialog handling.

### Changed

- Legacy browser presets are migrated into the active authenticated workspace; browser data is restored if migration cannot complete.
- Secret operation fields render as password inputs and are excluded from preset payloads before network submission.
- Watched-job polling supports multiple simultaneous jobs, stops after terminal states, and backs off while the browser tab is hidden.
- The Command Center now shows the active user/workspace preset scope explicitly.

### Fixed

- Removed the runtime dependency on `window.prompt()` for preset names.
- Fixed the previous job-watcher pattern that could recreate polling after a job had already reached a terminal state.
- Reduced accidental duplicate operation/job submissions from repeated button clicks.
- Pending preset-delete confirmation state is cleared when a dialog is cancelled with Escape.

### Security

- Preset records are stored in the server identity registry under `user_id + workspace_id`, rather than relying on browser local-storage namespaces as an access boundary.
- The server validates preset actions/fields against the shared operation catalog.
- Fields declared as `secret` are stripped again server-side as defense in depth.
- A preset ID from one user/workspace cannot be listed or deleted through another authenticated scope.

### Validation

- Added server-store regressions for per-user/workspace isolation, case-insensitive replacement, and cross-scope deletion denial.
- Added Web API regression coverage that saves a Wireless pairing preset containing a test pairing code and verifies that the secret is absent from the persisted/returned record.
- Added second-workspace preset isolation and delete regressions.
- Added source/HTML regressions for dialog assets, script ordering, secret masking, inline validation, job polling, busy states, and output copy controls.

## [3.7.0] - 2026-08-08

### Added

- First-party Web users with administrator and user roles.
- Per-user isolated Web workspace namespaces with an explicit workspace selector in the dashboard.
- First-run administrator setup and migration of an existing 3.6 workspace to the first administrator without moving its files.
- `adbgath web-user` commands for user listing, creation, password reset, disable, and enable.
- `adbgath web-workspace` commands for listing and creating a user's Web workspaces.
- Tenant-aware background job managers so queued work remains bound to the workspace selected when it was submitted.

### Fixed

- Security Audit and MASTG Web actions now use an explicit tenant-aware `/api/jobs` contract instead of the legacy validation boundary that could return HTTP 422.
- FastAPI structured validation errors are rendered as readable messages instead of `[object Object]` browser toasts.
- Existing Wireless, QR, Distributed Lab, uploads, jobs, and other first-party Web modules receive the 3.7 CSRF header transparently.
- User/workspace provisioning is transactionally serialized so duplicate records do not leave orphan workspace directories and concurrent first-run setup cannot create multiple initial administrators.
- Persistent server-secret creation tolerates concurrent Web-server startup without exposing partially initialized key material.
- Expired sessions are revoked before workspace selection can update active-workspace or last-used metadata.

### Security

- Passwords use scrypt with per-user random salts and the 3.7 profile `N=2^15`, `r=8`, `p=3`; plaintext passwords are never stored.
- Browser session tokens are random and only SHA-256 token hashes are stored in SQLite.
- Authenticated unsafe API requests require a session-bound HMAC CSRF token whose signing key remains server-only.
- Authentication forms validate same-origin `Origin`/`Referer` information when provided by the browser.
- WebSocket endpoints resolve the authenticated session before binding a workspace context and enforce session expiry for long-lived connections.
- Workspace selection is owner-scoped, including background jobs and artifact/project databases.
- Web administrative operations are bound to the authenticated server role instead of browser-supplied role claims.
- Disabling a user or resetting a password revokes that user's sessions.
- The final enabled administrator cannot be disabled.
- Server registry directories and secret/database files receive restrictive POSIX permissions where supported.

### Validation

- Added authentication-store tests for password/session hashing, revocation, workspace ownership, administrator safety, duplicate cleanup, and concurrent initial setup.
- Added Web integration tests for setup, login, CSRF, user isolation, workspace switching, logout, cross-user denial, authentication-origin checks, and WebSocket session expiry.
- Added explicit regression tests that queue and complete both `security` and `mastg` Web jobs without HTTP 422.
- Added concurrent server-secret initialization and expired-session workspace-mutation regressions.
- Added CLI parser coverage for the new Web user and workspace administration commands.

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
