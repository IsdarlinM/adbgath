# Web UI architecture

## Shared capability model

The web UI does not maintain an independent list of commands. On startup it retrieves the operation catalog from the backend and builds forms from field definitions, choices, requirements, destructive flags, and long-running flags.

```text
Browser form ── operation catalog ── strict payload validation ── AdbgathService
```

This prevents CLI/Web drift.

## Main workspaces

- Overview and diagnostics.
- Dynamic command center.
- Package/APK workspace with sorting, pagination, and multi-file staging.
- Live logcat with pause/resume, a bounded 5,000-line browser buffer, bookmarks, and local export.
- Security assessment.
- Projects and background jobs.
- Findings and snapshots.
- Artifact browser, project ZIP export, and downloads.
- Local browser presets for operation forms; presets do not leave the operator browser.
- Severity distribution visualization for structured findings.

## Jobs

Long-running actions can be queued. Job records contain:

- Action and normalized payload.
- Queued/running/completed/failed/cancelling/cancelled status.
- Progress.
- Timestamps.
- Result or sanitized failure state.

Cancellation is cooperative: it prevents queued work and marks active work as cancelling. A platform command already running may continue until its bounded timeout or next cancellation boundary.

## Local mode

```bash
adbgath web
```

Local mode binds to loopback by default and issues a random same-site HTTP-only cookie.

## Authenticated remote mode

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token "LONG_RANDOM_TOKEN" \
  --tls-cert server.crt \
  --tls-key server.key
```

All three remote requirements are mandatory. This mode is intended for an operator-controlled network, not public Internet exposure or untrusted multi-user hosting.

## WebSocket logcat

The log stream validates the session cookie and request Origin before opening. Package, regex, device, and format inputs pass through service validation.

## Uploads and artifacts

Uploads use basename normalization, collision-safe destination names, streaming size enforcement, and SHA-256 output. Downloads are resolved and confined to the configured workspace.

## Browser state and large streams

Operation presets are stored in `localStorage` under a versioned ADB-Gath key. They contain only catalogued form fields and are never treated as authorization for destructive actions. Destructive operations still require a fresh authorization confirmation.

The live logcat console keeps at most 5,000 lines in browser memory. Pausing stops rendering, not collection; resuming displays the newest retained buffer. Bookmarks are local references and can be exported with the visible log data.

## Wireless Debugging workspace

The Wireless view provides:

- ADB server and mDNS status.
- Pairing and connection service discovery.
- Secure six-digit pairing-code entry.
- Separate pairing and connection endpoint fields.
- Live mDNS monitoring over an authenticated WebSocket.
- Connect, disconnect, and auto-connect controls.
- Known-target aliases and local record removal.
- Diagnostics and an explicit ADB-Gath-scoped repair action.

Pairing-code fields use password input semantics. Codes are sent only to the synchronous execute endpoint, are never accepted by the persistent job endpoint, are removed from the browser field after use, and are excluded from local presets.

## Job cancellation

Background jobs execute ADB commands inside a cancellation context. Cancelling a running job signals the active child process, attempts graceful termination, and uses forced termination only after a short timeout. The job is then recorded as cancelled rather than completed.

## 3.4 QR pairing and shared wireless events

The Wireless workspace provides two explicit Android 11+ pairing paths: QR and six-digit code. QR creation requires authorized-target confirmation and is handled by dedicated endpoints rather than a persistent job. The SVG is protected by the local session, uses `Cache-Control: no-store`, and is removed from the page when the session terminates.

Session progress is delivered through `/ws/wireless/qr/{session_id}`. General device and mDNS changes are delivered through one shared `WirelessEventBroker`; browser clients no longer create independent discovery loops. QR secrets are never sent back to JavaScript or stored in browser storage.

Incremental inventory and schema-health operations remain available in the Command Center through the shared operation catalog.
