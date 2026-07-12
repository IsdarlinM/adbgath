# Web UI architecture

The adbgath web interface is a local FastAPI application packaged with static HTML, CSS, and JavaScript. It is not a remote control panel and does not expose an arbitrary terminal.

## Shared capability layer

Both interfaces call `AdbgathService`:

```text
CLI ───────────────┐
                   ├── AdbgathService ── AdbClient ── adb/adb.exe
Local web API ─────┘
```

This prevents command drift between platforms and keeps validation, timeouts, error handling, artifact paths, and security checks consistent.

## Available web actions

- Device discovery, root-state probe, wireless connect, and disconnect.
- Android user/profile discovery.
- Package inventory and APK path resolution.
- APK download, installation, uninstallation, and replacement.
- Device information and app permission summary.
- Runtime process/activity/service inspection.
- Timed log capture and live WebSocket logcat streaming.
- Network interface discovery, rooted packet capture, and tcpdump upload.
- Global HTTP proxy and ADB forward/reverse mappings.
- Debuggable app backup.
- Content-provider enumeration.
- Optional Frida process listing, attach, and spawn workflows.
- Local APK hashing and metadata analysis.
- Device posture audit, inventory, collection, and MASTG-oriented bundle.
- Dependency diagnostics.

## Security controls

- Loopback-only binding; non-loopback hosts are rejected.
- Same-site, HTTP-only local session cookie.
- Trusted-host middleware.
- Restrictive Content Security Policy and clickjacking protection.
- Action allowlist in the backend dispatcher.
- Literal `AUTHORIZED` confirmation for state-changing requests.
- No arbitrary command or raw ADB endpoint.
- Uploaded filenames are reduced to a basename.
- Upload limit of 512 MiB.
- Artifact downloads must resolve inside the configured workspace.
- No cross-origin API configuration.

## Starting the UI

```bash
adbgath web
adbgath web --port 9000
adbgath web --no-browser
```

The application intentionally avoids CDN assets so it remains usable in restricted lab environments and does not leak target context to third parties.
