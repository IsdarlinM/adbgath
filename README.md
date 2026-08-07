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
Developer: IsdarlinM | Version: 3.6.0
Threat intel • Device forensics • Defensive ADB workflow
```

**ADB-Gath 3.6.0** is a cross-platform Android assessment, evidence, and optional distributed-lab workspace for authorized security testing. It provides a native Windows/Linux CLI, a professional Web UI, persistent projects, reproducible evidence, static/runtime analysis, multi-device workflows, secure updates, and Android Wireless Debugging support.

> Use ADB-Gath only on devices, applications, accounts, and environments you own or are explicitly authorized to test.

## 3.6.0 highlights

- Preserves all 3.4 Wireless Debugging workflows: QR pairing, six-digit pairing, mDNS discovery, broker events, diagnostics, and Web UI.
- Adds a bounded asynchronous subprocess supervisor with cancellation, timeout, output limits, and Windows/POSIX process-tree cleanup.
- Adds a SHA-256 content-addressed artifact store with deduplication, optional compression, integrity verification, materialization, migration, and garbage collection.
- Adds RBAC roles (`viewer`, `analyst`, `operator`, `administrator`) with explicit approval for destructive remote operations.
- Adds an append-only SHA-256 hash-chained audit trail for policy decisions and distributed operations.
- Adds an optional distributed lab controller using **mutual TLS (mTLS)** plus per-agent bearer tokens. Agents connect outbound to the controller and never expose an arbitrary shell or raw ADB endpoint.
- Adds local PKI creation, controller certificates, agent enrollment, device pools, allowlisted distributed jobs, heartbeat/capability reporting, cancellation, and result collection.
- Adds Ed25519 signing and verification for plugin artifacts.
- Adds CycloneDX and SPDX SBOM generation for supply-chain visibility.
- Adds a dedicated responsive Distributed Lab Web workspace for agents, jobs, policy decisions, artifact integrity, and audit-chain verification.
- Extends formal SQLite migrations to schema version 360 while preserving backups and integrity validation.
- Adds static/runtime evidence correlation and retains existing projects, snapshots, reports, APK/AAB analysis, Frida observation, and Windows/Linux installers.

The original logo, banner, name, and visual identity are preserved.

## Architecture

```text
Windows CLI ───────┐
Linux CLI ─────────┼── Shared operation catalog ── AdbgathService ── AdbClient ── adb/adb.exe
Web UI + Jobs ─────┘                    │
                                       ├── Wireless broker / QR coordinator
                                       ├── Async process supervisor
                                       ├── Projects / schema migrations / CAS evidence
                                       ├── RBAC / audit / signed plugins
                                       ├── Optional mTLS lab controller + outbound agents
                                       └── APK / Bundle / static-runtime correlation
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

## Distributed lab (optional)

The local CLI and Web UI remain the default. Distributed mode is opt-in and requires mTLS.

Create a local CA and controller certificate:

```bash
adbgath lab pki-init --dir ./lab-pki
adbgath lab controller-cert --dir ./lab-pki --host 127.0.0.1
```

Enroll an outbound agent:

```bash
adbgath lab agent-enroll lab-windows-01 --pki-dir ./lab-pki --controller https://127.0.0.1:9443
```

Start the controller using the generated certificate paths:

```bash
adbgath lab controller --host 127.0.0.1 --port 9443 --cert ./lab-pki/controller-adbgath-controller-cert.pem --key ./lab-pki/controller-adbgath-controller-key.pem --ca ./lab-pki/ca-cert.pem
```

On the enrolled worker, run the generated agent configuration:

```bash
adbgath lab agent-run --config ./lab-pki/agent-lab-windows-01.json
```

Submit only catalogued operations:

```bash
adbgath lab job-submit --agent lab-windows-01 --action devices --role viewer
adbgath lab jobs
adbgath audit verify
```

Distributed agents do not expose a shell and reject controller, updater, Web-server, and other non-agent operations. Destructive operations require an operator/administrator role plus explicit `--approved`.

The local Web UI adds `/lab` for agents, jobs, policy checks, artifact integrity, and audit history.

See [`docs/DISTRIBUTED_LAB.md`](docs/DISTRIBUTED_LAB.md).

## Content-addressed evidence

```bash
adbgath artifact-store status
adbgath artifact-store import --path evidence.log --project-id PROJECT
adbgath artifact-store verify
adbgath artifact-store gc            # dry-run
adbgath artifact-store gc --apply    # remove only unreferenced objects
```

Identical SHA-256 content is stored once and referenced by logical project/session records.

## Supply chain

```bash
adbgath sbom --format cyclonedx --output cyclonedx.json
adbgath sbom --format spdx --output spdx.json
adbgath plugin keygen --private-key publisher.key --public-key publisher.pub
adbgath plugin sign --manifest plugin.json --plugin-file plugin.py --private-key publisher.key --output plugin.sig.json
adbgath plugin verify --bundle plugin.sig.json --plugin-file plugin.py --public-key publisher.pub
```

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
