# Web UI architecture

## Shared capability model

The Web UI does not maintain an independent list of commands. On startup it retrieves the operation catalog from the backend and builds forms from field definitions, choices, requirements, destructive flags, and long-running flags.

```text
Browser form ── operation catalog ── strict payload validation ── AdbgathService
```

This prevents CLI/Web drift and keeps the browser away from arbitrary shell or raw ADB execution endpoints.

## Main dashboard views

- Overview and diagnostics.
- Dynamic Command Center.
- Package/APK workspace with sorting, pagination, and multi-file staging.
- Live Logcat with pause/resume, a bounded 5,000-line browser buffer, bookmarks, and local export.
- Security assessment.
- Projects and background jobs.
- Findings and snapshots.
- Artifact browser, project ZIP export, and downloads.
- Wireless Debugging, including QR/code pairing and advanced controls.
- Distributed Lab inside the same dashboard shell.
- Administrator-only Web user management.

All first-party views use the unified dark/green ADB-Gath visual system.

## 3.7 authentication and workspace context

The top bar separates:

```text
TARGET DEVICE   selected ADB device/transport
PROFILE         Android OS user/profile
WORKSPACE       authenticated ADB-Gath workspace
```

Web requests resolve `user_id + active_workspace_id` before selecting the service/database context. A browser-supplied workspace ID is checked against the authenticated owner before use.

See [`WEB_AUTH_3_7.md`](WEB_AUTH_3_7.md) for the authentication, CSRF, session, remote bootstrap, and workspace-isolation model.

## Command Center presets in 3.7.1

The native browser prompt used to name presets is superseded by an ADB-Gath themed `<dialog>`.

Presets are no longer actively stored in one browser `localStorage` namespace. They are persisted in the server identity registry and scoped by:

```text
user_id + workspace_id
```

The preset API is:

```text
GET    /api/presets
POST   /api/presets
DELETE /api/presets/{preset_id}
```

All unsafe requests are covered by the normal authenticated-session/CSRF middleware.

Preset security properties:

- only actions present in the shared operation catalog are accepted;
- undeclared fields are rejected;
- fields declared as `secret` are removed client-side before the preset request and stripped again server-side;
- preset IDs are resolved only inside the authenticated user/workspace scope;
- the same name, case-insensitively, replaces an existing preset in that workspace;
- each workspace stores at most 100 presets;
- presets never satisfy destructive-action authorization: a destructive operation still requires a fresh authorization confirmation at execution time.

### Legacy preset migration

ADB-Gath 3.7.1 recognizes the old browser preset key and the short-lived 3.7.1 development namespace. During Command Center initialization it temporarily detaches those values so the older client code cannot consume them, imports sanitized entries through `/api/presets`, and removes the browser copy only when migration succeeds.

If migration fails, the original browser value is restored so the user does not lose the preset data.

## Command Center form UX

3.7.1 adds:

- inline required-field and numeric range errors;
- focus and scroll to the first invalid field;
- password rendering for catalog fields typed as `secret`;
- busy/disabled execution state to reduce accidental duplicate requests;
- themed save/replace/delete preset dialogs;
- a visible user/workspace preset-scope hint;
- copy-to-clipboard controls on structured output panels.

The implementation layers these behaviors after the established `app.js`/`app370.js` clients so existing operation rendering and authentication remain the source of truth.

## Jobs

Long-running actions can be queued. Job records contain:

- Action and normalized payload.
- Queued/running/completed/failed/cancelling/cancelled status.
- Progress.
- Timestamps.
- Result or sanitized failure state.

3.7.1 watches multiple submitted jobs using a bounded `setTimeout` polling loop. Terminal jobs are removed from the watch set and do not restart polling. Polling backs off while the document is hidden. This replaces the older single-interval pattern that could restart after a terminal result.

Job cancellation remains cooperative: it prevents queued work and marks active work as cancelling. A platform command already running may continue until its bounded timeout or next cancellation boundary.

Cancelling a job now uses a themed confirmation dialog. Already-created evidence is retained.

## Security Audit / MASTG

`security` and `mastg` are long-running workspace-scoped jobs. ADB-Gath 3.7 fixed their Web `/api/jobs` contract and structured error rendering; 3.7.1 adds busy states so repeated clicks do not enqueue accidental duplicate runs from the same control.

## Local mode

```bash
adbgath web
```

Local mode binds to loopback by default. After 3.7 first-run setup, users authenticate with individual accounts.

## Authenticated remote mode

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token "LONG_RANDOM_TOKEN" \
  --tls-cert server.crt \
  --tls-key server.key
```

TLS and the startup token remain mandatory for non-loopback mode. When no users exist, the same startup token is required on the first-administrator form. After bootstrap, individual Web accounts are used.

This mode is intended for an operator-controlled network, not direct public-Internet exposure.

## WebSocket Logcat

The log stream validates the authenticated session and request Origin before opening. Package, regex, device, and format inputs pass through service validation.

The live console keeps at most 5,000 lines in browser memory. Pausing stops rendering, not collection; resuming displays the newest retained buffer. Bookmarks are local references and can be exported with the visible log data.

Clearing the device Logcat buffer is a state-changing action and now requires a themed confirmation from the Web UI.

## Uploads and artifacts

Uploads use basename normalization, collision-safe destination names, streaming size enforcement, and SHA-256 output. Downloads are resolved and confined to the active authenticated workspace.

## Wireless Debugging

The integrated Wireless view provides:

- ADB server and mDNS status.
- QR pairing and secure six-digit pairing-code entry.
- Pairing and connection service discovery.
- Separate pairing and connection endpoint fields.
- Live mDNS monitoring over an authenticated WebSocket.
- Connect, disconnect, and auto-connect controls.
- Known-target aliases and local record removal.
- Diagnostics and an explicit ADB-Gath-scoped repair action.

Pairing-code fields use password semantics. Codes are sent only to pairing endpoints, are never accepted by persistent background jobs, are removed from browser fields after use, and are excluded from presets.

## QR pairing and shared wireless events

The Wireless workspace provides two explicit Android 11+ pairing paths: QR and six-digit code. QR creation requires authorized-target confirmation and is handled by dedicated endpoints rather than a persistent job. The SVG is protected by the authenticated session, uses `Cache-Control: no-store`, and is removed from the page when the session terminates.

Session progress is delivered through `/ws/wireless/qr/{session_id}`. General device and mDNS changes are delivered through one shared `WirelessEventBroker`; browser clients do not create independent discovery loops. QR secrets are never sent back to JavaScript or stored in preset records.

## Accessibility and interaction states

The 3.7.1 UX layer uses native `<dialog>` semantics where supported, keyboard cancellation, themed backdrops, explicit focus placement, `aria-busy` on long actions, and an ARIA live region for toast status.

Reduced-motion preferences are respected by the additional UX stylesheet.
