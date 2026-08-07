# adbgath

```text
 █████╗ ██████╗ ██████╗       ██████╗  █████╗ ████████╗██╗  ██╗███████╗██████╗ 
██╔══██╗██╔══██╗██╔══██╗     ██╔════╝ ██╔══██╗╚══██╔══╝██║  ██║██╔════╝██╔══██╗
███████║██║  ██║██████╔╝█████╗██║  ███╗███████║   ██║   ███████║█████╗  ██████╔╝
██╔══██║██║  ██║██╔══██╗╚════╝██║   ██║██╔══██║   ██║   ██╔══██║██╔══╝  ██╔══██╗
██║  ██║██████╔╝██████╔╝      ╚██████╔╝██║  ██║   ██║   ██║  ██║███████╗██║  ██║
╚═╝  ╚═╝╚═════╝ ╚═════╝        ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝

ADB-Gath
Defensive ADB Toolkit
ADB-Gathering
Developer: IsdarlinM | Version: 3.4.0
Threat intel • Device forensics • Defensive ADB workflow
```

**ADB-Gath 3.4.0** is a cross-platform Android assessment and evidence workspace for authorized security testing. It provides a native Windows/Linux CLI, a professional Web UI, persistent projects, reproducible evidence, static/runtime analysis, multi-device workflows, secure updates, and Android Wireless Debugging support.

> Use ADB-Gath only on devices, applications, accounts, and environments you own or are explicitly authorized to test.

## 3.4.0 highlights

- Android 11+ Wireless Debugging through both **QR pairing** and **six-digit pairing code**.
- AOSP-compatible QR payload: `WIFI:T:ADB;S:studio-<instance>;P:<secret>;;`.
- QR secrets held only in memory and sent to `adb pair` through standard input.
- Shared ADB/mDNS event broker for ordered device and service events.
- Formal SQLite migrations with checksums, backups, integrity validation, and rollback.
- Incremental inventory capture, history, comparison, watch mode, stable digests, and retention.
- Cached device capabilities with explicit refresh.
- Professional Wireless Web workspace with no-store QR delivery, WebSocket status, diagnostics, known targets, aliases, pairing, connection, and cancellation.
- Existing 3.3 capabilities retained: Windows/Linux installers, transactional APK replacement, split APK/APKS/AAB support, evidence manifests, snapshots, reports, plugins, Frida observation, projects, jobs, and secure update rollback.

The original logo, banner, name, and visual identity are preserved.

## Architecture

```text
Windows CLI ───────┐
Linux CLI ─────────┼── Shared operation catalog ── AdbgathService ── AdbClient ── adb/adb.exe
Web UI + Jobs ─────┘                    │
                                       ├── Wireless broker / QR coordinator
                                       ├── Projects / SQLite migrations
                                       ├── Rules / Plugins
                                       ├── Evidence / Reports
                                       └── APK / Bundle analysis
```

Host processes use argument arrays with `shell=False`. The browser has no arbitrary shell or arbitrary ADB command endpoint.

## Requirements

Required:

- Python 3.11 or newer.
- Android SDK Platform-Tools (`adb`).
- An authorized Android device or emulator.

Optional:

- Java and `bundletool` for AAB/APKS workflows.
- `aapt`, `aapt2`, `apkanalyzer`, and `apksigner` for richer static analysis.
- Frida tools for controlled observation.
- Root and `tcpdump` for device-side packet capture.

No executables, APKs, JARs, PCAPs, or other platform binaries are committed to the repository.

## Windows installation

```bat
installers\windows\install.cmd
```

Open a new terminal:

```bat
adbgath --version
adbgath doctor --fix
adbgath devices
adbgath web
```

Portable mode:

```bat
installers\windows\portable.cmd
```

Uninstall while retaining projects and evidence:

```bat
installers\windows\uninstall.cmd -KeepWorkspace
```

See [`docs/WINDOWS.md`](docs/WINDOWS.md).

## Linux installation

```bash
chmod +x installers/linux/install.sh
./installers/linux/install.sh
```

Portable mode:

```bash
./installers/linux/portable.sh ./portable-adbgath
```

## Wireless Debugging

### Pair with QR

On Android, open **Developer options → Wireless debugging → Pair device with QR code**, then run:

```bash
adbgath wireless qr
```

Options:

```bash
adbgath wireless qr --timeout 180
adbgath wireless qr --no-auto-connect
adbgath wireless qr --output ./pairing.svg --open
adbgath wireless broker status
```

The QR session expires automatically. The secret is excluded from command arguments, SQLite, jobs, metrics, reports, browser storage, and logs.

### Pair with six-digit code

On Android, select **Pair device with pairing code** and keep the dialog open:

```bash
adbgath wireless discover
adbgath wireless pair 192.168.1.50:37123
```

After pairing, connect to the separate connection endpoint shown by Android:

```bash
adbgath wireless connect 192.168.1.50:41267
```

The pairing and connection ports normally differ.

Other commands:

```bash
adbgath wireless status
adbgath wireless diagnose
adbgath wireless diagnose --fix
adbgath wireless known
adbgath wireless auto-connect
adbgath wireless watch
```

See [`docs/WIRELESS.md`](docs/WIRELESS.md).

## Web UI

```bash
adbgath web
```

Default address:

```text
http://127.0.0.1:8765
```

The Web UI includes device/profile selection, dynamic operation forms, package/APK workspace, live logcat, Wireless Debugging, projects, jobs, findings, snapshots, evidence, reports, and artifact downloads.

Remote mode is opt-in and requires TLS plus a long operator token:

```bash
adbgath web --host 0.0.0.0 \
  --remote-token "LONG_RANDOM_OPERATOR_TOKEN" \
  --tls-cert ./server.crt \
  --tls-key ./server.key
```

Plaintext non-loopback mode is rejected.

## Assessment workflows

```bash
adbgath --device SERIAL --user current list packages --include-paths
adbgath --device SERIAL assess com.example.app
adbgath --device SERIAL evidence --package com.example.app --output ./evidence
adbgath static ./app.apk --output ./reports/app-static.json
adbgath project list
adbgath findings --project-id PROJECT_ID
adbgath report PROJECT_ID --format html
adbgath report PROJECT_ID --format sarif
```

Incremental inventory:

```bash
adbgath --device SERIAL inventory capture --name before
adbgath inventory list
adbgath inventory diff BEFORE_ID AFTER_ID
adbgath --device SERIAL inventory watch --interval 10
adbgath schema
```

## Development and validation

```bash
python -m venv .venv
. .venv/bin/activate                # Linux
# .venv\Scripts\activate           # Windows
python -m pip install -e ".[dev]"
ruff check .
python -m compileall -q src
pytest
node --check src/adbgath/web/static/app.js
node --check src/adbgath/web/static/wireless340.js
python -m build
```

## Documentation

- [`docs/QUICKSTART.md`](docs/QUICKSTART.md)
- [`docs/WIRELESS.md`](docs/WIRELESS.md)
- [`docs/WEB_UI.md`](docs/WEB_UI.md)
- [`docs/SECURITY.md`](docs/SECURITY.md)
- [`docs/WINDOWS.md`](docs/WINDOWS.md)
- [`docs/IMPLEMENTATION_REPORT.md`](docs/IMPLEMENTATION_REPORT.md)
- [`docs/ROADMAP_3_5_3_6.md`](docs/ROADMAP_3_5_3_6.md)

## License

See [`LICENSE`](LICENSE).
