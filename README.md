# adbgath

```text
 █████╗ ██████╗ ██████╗        ██████╗  █████╗ ████████╗██╗  ██╗███████╗██████╗ 
██╔══██╗██╔══██╗██╔══██╗      ██╔════╝ ██╔══██╗╚══██╔══╝██║  ██║██╔════╝██╔══██╗
███████║██║  ██║██████╔╝█████╗██║  ███╗███████║   ██║   ███████║█████╗  ██████╔╝
██╔══██║██║  ██║██╔══██╗╚════╝██║   ██║██╔══██║   ██║   ██╔══██║██╔══╝  ██╔══██╗
██║  ██║██████╔╝██████╔╝      ╚██████╔╝██║  ██║   ██║   ██║  ██║███████╗██║  ██║
╚═╝  ╚═╝╚═════╝ ╚═════╝        ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝

ADB-Gath
Defensive ADB Toolkit
ADB-Gathering
Developer: IsdarlinM | Version: 3.3.0
Threat intel • Device forensics • Defensive ADB workflow
```

**ADB-Gath 3.3.0** is a cross-platform Android assessment and evidence workspace for authorized security testing. It provides a native Windows/Linux CLI, a professional local Web UI, persistent projects, reproducible evidence, APK analysis and secure Wireless Debugging management.

> Use ADB-Gath only on devices, applications, accounts and environments you own or are explicitly authorized to test.

## Highlights

- Native Windows and Linux operation without a Bash-dependent core.
- Original ADB-Gath branding preserved and protected by regression tests.
- CLI and Web UI backed by the same allowlisted operation catalog.
- Android 11+ Wireless Debugging using the six-digit pairing-code workflow.
- mDNS discovery of separate pairing and connection services.
- Semantic ADB failure detection, including exit-code `0` responses containing `failed to connect` or Windows error `10061`.
- Persistent projects, sessions, findings, artifacts, snapshots, groups, jobs, wireless targets and local performance metrics.
- Transactional APK replacement with backup and rollback.
- APK, split APK, `.apks` and optional AAB/bundletool workflows.
- Static Android attack-surface analysis and controlled runtime/evidence collection.
- JSON, Markdown, HTML, CSV, SARIF and PDF reports.
- Permission-declaring plugins and observation-only Frida scripts.
- Secure update staging and rollback.
- Windows/Linux installation, repair, portable and offline-cache modes.

## Architecture

```text
Windows CLI ───────┐
Linux CLI ─────────┼── Shared operation catalog ── AdbgathService ── AdbClient ── adb/adb.exe
Web UI + Jobs ─────┘                    │
                                       ├── Wireless / mDNS / pairing
                                       ├── Projects / SQLite
                                       ├── Evidence / reports
                                       ├── Rules / plugins
                                       └── APK / bundle analysis
```

Host commands are passed as argument arrays with `shell=False`. The browser has no arbitrary shell or arbitrary ADB-command endpoint.

## Requirements

Required:

- Python 3.11 or newer.
- Android SDK Platform-Tools (`adb`).
- An authorized Android device or emulator.

Optional:

- Java and `bundletool` for AAB/APKS workflows.
- `aapt`, `aapt2`, `apkanalyzer` and `apksigner` for richer static metadata.
- Frida tools for controlled runtime observation.
- Root and `tcpdump` for device-side packet capture.

No executables, APKs, JARs, PCAPs or other platform binaries are committed to the repository.

## Installation

### Windows

```bat
installers\windows\install.cmd
```

Open a new terminal afterward:

```bat
adbgath --version
adbgath doctor --fix
adbgath devices
adbgath web
```

Useful modes:

```bat
installers\windows\install.cmd -Repair
installers\windows\install.cmd -Force
installers\windows\install.cmd -SkipFrida
installers\windows\install.cmd -SkipBundletool
installers\windows\install.cmd -OfflineCache "D:\adbgath-cache"
installers\windows\portable.cmd
```

### Linux

```bash
chmod +x installers/linux/install.sh
./installers/linux/install.sh
```

Portable mode:

```bash
./installers/linux/portable.sh ./portable-adbgath
```

## Wireless Debugging with pairing code

Android 11+ normally presents **two different ports**:

1. A temporary pairing endpoint under **Pair device with pairing code**.
2. A separate connection endpoint on the main **Wireless debugging** screen.

Discover advertised services:

```bash
adbgath wireless discover
```

Pair while the Android code dialog remains open:

```bash
adbgath wireless pair 172.18.9.245:42029
```

ADB-Gath requests the six-digit code through hidden terminal input. The code is sent to `adb pair` through standard input and is not stored in arguments, shell history, SQLite, jobs, metrics, reports or artifacts.

Then connect using the separate connection port:

```bash
adbgath wireless connect 172.18.9.245:40587
adbgath devices --details
```

A short pairing alias is also available:

```bash
adbgath pair 172.18.9.245:42029
```

Additional commands:

```bash
adbgath wireless status
adbgath wireless watch --interval 3
adbgath wireless diagnose
adbgath wireless diagnose --fix --persist
adbgath wireless auto-connect
adbgath wireless known
adbgath wireless alias TARGET_ID "SOC Android Lab"
adbgath wireless forget TARGET_ID
```

Legacy USB-assisted TCP/IP mode:

```bash
adbgath --device USB_SERIAL wireless tcpip --port 5555
```

See [`docs/WIRELESS.md`](docs/WIRELESS.md).

## Web UI

Start locally:

```bash
adbgath web
```

Dashboard:

```text
http://127.0.0.1:8765
```

Wireless workspace:

```text
http://127.0.0.1:8765/wireless
```

The Wireless page includes:

- ADB server and mDNS status.
- Pairing and connection service discovery.
- Live updates through an authenticated WebSocket.
- Password-style six-digit code entry.
- Pair, connect, disconnect and auto-connect controls.
- Diagnostics and ADB-Gath-scoped mDNS repair.
- Known targets, aliases and local record removal.

Pairing requires explicit authorized-target confirmation and cannot be queued as a persistent background job.

Remote Web mode is opt-in and requires TLS plus a long operator token:

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token "use-a-long-random-operator-token" \
  --tls-cert ./server.crt \
  --tls-key ./server.key
```

Plaintext non-loopback mode is rejected.

## Common workflows

List profiles and applications:

```bash
adbgath --device SERIAL list users
adbgath --device SERIAL --user current list packages --include-paths
```

Pull and inspect an APK set:

```bash
adbgath --device SERIAL --user current download com.example.app --output ./apks
adbgath static ./apks/base.apk --output ./reports/static.json
```

Install or transactionally replace:

```bash
adbgath --device SERIAL --user 0 install ./app.apk --replace
adbgath --device SERIAL --user 0 install-set ./split-directory
adbgath --device SERIAL --user 0 replace com.example.app ./replacement.apk
```

`replace` preserves the installed application when in-place replacement fails. Add `--allow-uninstall` only after reviewing signature and data-loss implications.

Create a project and run a reproducible assessment:

```bash
adbgath project create "Authorized assessment" --scope com.example.app
adbgath --device SERIAL assess com.example.app --project-id PROJECT_ID
```

Capture evidence:

```bash
adbgath --device SERIAL evidence --package com.example.app --screen-record 15 --output ./evidence
```

Export reports:

```bash
adbgath report PROJECT_ID --format html
adbgath report PROJECT_ID --format pdf
adbgath report PROJECT_ID --format sarif
adbgath project export PROJECT_ID --output ./project-evidence.zip
```

## Device and performance modes

```bash
adbgath devices --fast
adbgath devices --details
adbgath devices --watch --duration 30
adbgath metrics summary
adbgath metrics list --limit 100
adbgath metrics clear
```

Local metrics contain command category, duration, byte counts, return code, semantic success and cancellation state. No telemetry is transmitted.

## Security boundaries

- No host `shell=True` execution.
- No browser terminal or arbitrary ADB command.
- Strict operation allowlist and payload validation.
- Explicit device/profile selection for application-changing operations.
- Explicit Web confirmation for destructive operations.
- Pairing codes accepted only through transient secret input.
- Workspace-confined uploads and downloads.
- Loopback-only Web mode by default.
- TLS/token requirement for optional remote mode.
- ZIP traversal, symlink and decompression limits in updates.
- Plugin permission declarations and explicit approval.

See:

- [`docs/SECURITY.md`](docs/SECURITY.md)
- [`docs/WEB_UI.md`](docs/WEB_UI.md)
- [`docs/WINDOWS.md`](docs/WINDOWS.md)
- [`docs/WIRELESS.md`](docs/WIRELESS.md)
- [`docs/PLUGIN_API.md`](docs/PLUGIN_API.md)

## Development

```bash
python -m venv .venv
. .venv/bin/activate                # Linux
# .venv\Scripts\activate           # Windows
python -m pip install -e ".[dev]"
ruff check .
python -m compileall -q src
pytest
node --check src/adbgath/web/static/app.js
node --check src/adbgath/web/static/wireless.js
python -m build
```

CI definitions cover Windows and Ubuntu, Python 3.11–3.13, the Windows installer and an Android emulator. A physical-device Wireless Debugging matrix remains a manual laboratory validation because GitHub-hosted runners cannot present a real Android pairing dialog.

## License

See [`LICENSE`](LICENSE).
