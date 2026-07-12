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
Developer: IsdarlinM | Version: 3.2.9
Threat intel • Device forensics • Defensive ADB workflow
```

**adbgath 3.2.9** is a cross-platform Android assessment and evidence workspace for authorized security testing. It provides a native Windows and Linux CLI, a professional web UI, persistent projects, reproducible evidence, static and device-side analysis, multi-device workflows, and secure update/rollback support.

The CLI and web interface use the same Python service layer and shared operation catalog. A capability added to the catalog is therefore validated and exposed consistently across Windows, Linux, CLI, and Web UI.

> Use adbgath only on devices, applications, accounts, and environments you own or are explicitly authorized to test.

## What 3.2.9 adds

- Native Windows and Linux operation without Bash-dependent core logic.
- Owner-approved ADB-Gath branding restored and protected by regression tests.
- Transactional application replacement with APK backup and rollback.
- APK, split APK, `.apks`, and optional Android App Bundle workflows.
- Static Android attack-surface analysis for manifest components, deep links, permissions, cleartext policy, backup policy, WebView indicators, signing, native libraries, endpoints, and embedded-secret indicators.
- Persistent SQLite projects, sessions, findings, artifacts, snapshots, groups, and background jobs.
- Evidence capture with screenshots, bugreports, dumpsys data, logcat, APK sets, SHA-256 hashes, redacted copies, and optional HMAC-signed manifests.
- Snapshot comparison for device/application state changes.
- Concurrent read-only execution across named device groups.
- Report export to JSON, Markdown, HTML, CSV, SARIF, and PDF.
- Controlled, versioned Frida observation scripts with syntax validation, redacted session logs, and persistent history.
- Permission-declaring plugin API with explicit operator approval.
- Local web UI by default, with optional TLS-only authenticated remote mode.
- Secure local ZIP update workflow with checksum validation, path/type limits, preserved data, smoke testing, automatic restoration, and rollback.
- Windows/Linux portable and offline-capable installation modes.
- Project ZIP export with metadata, findings, sessions, snapshots, artifact hashes, and workspace-confined evidence.
- Saved local operation presets, package sorting/pagination, multi-file staging, bounded logcat rendering, bookmarks, export, and severity visualization in the Web UI.

## Architecture

```text
Windows CLI ───────┐
Linux CLI ─────────┼── Shared operation catalog ── AdbgathService ── AdbClient ── adb/adb.exe
Web UI + Jobs ─────┘                    │
                                       ├── Projects / SQLite
                                       ├── Rules / Plugins
                                       ├── Evidence / Reports
                                       └── APK / Bundle analysis
```

Host commands are executed as argument arrays with `shell=False`. The browser has no arbitrary shell or arbitrary ADB endpoint.

## Requirements

Required:

- Python 3.11 or newer.
- Android SDK Platform-Tools (`adb`).
- An authorized Android device or emulator with USB or Wireless Debugging enabled.

Optional:

- Java and `bundletool` for AAB/APKS build, device-spec, and install workflows.
- `aapt`, `aapt2`, `apkanalyzer`, and `apksigner` for richer static metadata.
- Frida tools for controlled runtime observation.
- Root and `tcpdump` for device-side packet capture.

The installers can provision the required host dependencies. No executables, APKs, JARs, PCAPs, or other platform binaries are committed to this repository.

## Windows installation

From Command Prompt or Windows Terminal:

```bat
installers\windows\install.cmd
```

Open a new terminal after installation:

```bat
adbgath --version
adbgath doctor --fix
adbgath devices
adbgath web
```

Useful installer modes:

```bat
installers\windows\install.cmd -Repair
installers\windows\install.cmd -Force
installers\windows\install.cmd -SkipFrida
installers\windows\install.cmd -SkipBundletool
installers\windows\install.cmd -SkipPlatformTools
installers\windows\install.cmd -OfflineCache "D:\adbgath-cache"
installers\windows\install.cmd -Proxy "http://proxy.example:8080"
```

Portable installation without persistent environment changes:

```bat
installers\windows\portable.cmd
portable-adbgath\bin\adbgath.cmd doctor
```

Uninstall while preserving projects/evidence:

```bat
installers\windows\uninstall.cmd -KeepWorkspace
```

See [`docs/WINDOWS.md`](docs/WINDOWS.md).

## Linux installation

```bash
chmod +x installers/linux/install.sh
./installers/linux/install.sh
```

Options:

```bash
./installers/linux/install.sh --skip-frida
./installers/linux/install.sh --skip-bundletool
./installers/linux/install.sh --offline-cache /media/cache
./installers/linux/install.sh --proxy http://proxy.example:8080
./installers/linux/install.sh --force
```

Portable mode:

```bash
./installers/linux/portable.sh ./portable-adbgath
./portable-adbgath/bin/adbgath doctor
```

## Web UI

Start locally:

```bash
adbgath web
```

Default URL:

```text
http://127.0.0.1:8765
```

The local interface includes:

- Device and Android profile selection.
- Capability and dependency diagnostics.
- Dynamic forms generated from the shared operation catalog.
- Package/APK workspace with sorting, pagination, secure multi-file uploads, and local browser presets.
- Live WebSocket logcat with a bounded 5,000-line client buffer, pause/resume, bookmarks, and local export.
- Persistent projects, sessions, jobs, findings, snapshots, and artifacts.
- Background execution, progress, cancellation state, retry-oriented history, and downloadable outputs.
- Static/dynamic assessment panels and professional report export.

Remote mode is opt-in. Non-loopback binding requires both TLS and an operator token of at least 24 characters:

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token "use-a-long-random-operator-token" \
  --tls-cert ./server.crt \
  --tls-key ./server.key
```

Plaintext remote mode is rejected. Local loopback mode remains the default and needs no login.

See [`docs/WEB_UI.md`](docs/WEB_UI.md) and [`docs/SECURITY.md`](docs/SECURITY.md).

## CLI help

Every command provides command-specific help:

```bash
adbgath -h
adbgath COMMAND -h
adbgath COMMAND --help
```

Running `adbgath` with no arguments starts interactive mode.

Global selection examples:

```bash
adbgath --device emulator-5554 list users
adbgath --device emulator-5554 --user current list packages --include-paths
adbgath --connect 192.168.1.50:5555 --device 192.168.1.50:5555 info all
```

State-changing application operations require an explicit device and Android profile.

## APK and bundle workflows

Pull all APK splits for a package:

```bash
adbgath --device SERIAL --user current download com.example.app --output ./apks
```

Install a single APK:

```bash
adbgath --device SERIAL --user 0 install ./app.apk --replace
```

Install a split directory or `.apks` archive:

```bash
adbgath --device SERIAL --user 0 install-set ./split-directory
adbgath --device SERIAL --user 0 install-set ./application.apks
```

Transactional replacement:

```bash
# Safe first attempt: existing app is preserved if in-place replacement fails.
adbgath --device SERIAL --user 0 replace com.example.app ./replacement.apk

# Explicitly permit uninstall/install fallback and automatic APK rollback.
adbgath --device SERIAL --user 0 replace com.example.app ./replacement.apk --allow-uninstall
```

Bundletool workflows:

```bash
adbgath bundle inspect app.aab
adbgath --device SERIAL bundle device-spec --output device-spec.json
adbgath bundle build-apks app.aab --output app.apks
adbgath --device SERIAL bundle install-apks app.apks
adbgath bundle extract app.apks --output ./extracted
```

## Static and runtime analysis

```bash
adbgath static ./app.apk --output ./reports/app-static.json
adbgath --device SERIAL app com.example.app
adbgath --device SERIAL runtime summary --package com.example.app
adbgath --device SERIAL content --package com.example.app
```

Static findings include evidence, severity, confidence, component, impact, safe validation guidance, false-positive conditions, mitigation, and references.

## Reproducible assessment workflow

Create a project:

```bash
adbgath project create "Example assessment" --scope com.example.app
adbgath project list
```

Run a full authorized workflow:

```bash
adbgath --device SERIAL assess com.example.app --project-id PROJECT_ID
```

The assessment records a session, captures evidence, downloads APKs, runs static analysis, saves findings, and exports JSON, Markdown, HTML, SARIF, and PDF artifacts.

Findings lifecycle:

```bash
adbgath findings --project-id PROJECT_ID
adbgath findings --set-status FINDING_ID validated
```

Report export:

```bash
adbgath report PROJECT_ID --format html
adbgath report PROJECT_ID --format pdf
adbgath report PROJECT_ID --format sarif
adbgath project export PROJECT_ID --output ./project-evidence.zip
```

## Evidence and chain of custody

```bash
adbgath --device SERIAL evidence --package com.example.app --screen-record 15 --output ./evidence
```

Collected evidence can include:

- Device/build metadata and capabilities.
- Android users and package inventory.
- Logcat, properties, activities, windows, and package dumps.
- Screenshot, optional screen recording, and bugreport.
- Base and split APKs.
- SHA-256 for every artifact.
- Exact command, return code, duration, timestamps, device serial, tool version, and ADB version.
- Redacted text copies for tokens, cookies, authorization values, emails, and phone-like data.

To create an HMAC signature alongside the manifest:

```bash
export ADBGATH_MANIFEST_HMAC_KEY='store-this-key-securely'
adbgath --device SERIAL evidence --package com.example.app
```

## Snapshots and differences

```bash
adbgath --device SERIAL snapshot create before --project-id PROJECT_ID --package com.example.app
# Perform an authorized test or configuration change.
adbgath --device SERIAL snapshot create after --project-id PROJECT_ID --package com.example.app
adbgath snapshot diff before after --output ./diff.json
```

## Multi-device groups

```bash
adbgath group add lab emulator-5554
adbgath group add lab RF8M...
adbgath group list
adbgath run-group lab inventory
adbgath run-group lab security
```

Group execution is restricted to read-only inventory, information, security, and capability operations.

## Logcat, network, and Frida

```bash
adbgath --device SERIAL logs listen --package com.example.app
adbgath --device SERIAL logs capture --duration 60 --regex "exception|security" --output app.log
adbgath --device SERIAL proxy set 127.0.0.1:8080
adbgath --device SERIAL forward reverse 8080 8080
adbgath --device SERIAL sniff interfaces
adbgath --device SERIAL sniff capture --interface wlan0 --duration 30 --output capture.pcap
```

Bundled Frida scripts are observation-only:

```bash
adbgath frida scripts
adbgath --device SERIAL frida attach --package com.example.app --script tls-observer
adbgath --device SERIAL frida spawn --package com.example.app --script webview-observer
adbgath frida history --limit 50
```

Script files are limited to JavaScript, bounded in size, and syntax-checked with Node.js when available. Stored Frida stdout/stderr is redacted by default and linked to a persistent session record. They do not disable TLS pinning, export plaintext keys, bypass authentication, or alter the target application.

## Plugins

Plugins are discovered through the `adbgath.plugins` Python entry-point group. Each plugin must declare its permissions from:

```text
read_device
write_device
network
filesystem
```

List plugins:

```bash
adbgath plugin list
```

Run only after approving every declared permission:

```bash
adbgath --device SERIAL plugin run example-plugin \
  --allow-permission read_device \
  --allow-permission filesystem
```

See [`docs/PLUGIN_API.md`](docs/PLUGIN_API.md).

## Secure update and rollback

Check the official release metadata:

```bash
adbgath update check
```

Review a local update plan:

```bash
adbgath update plan --archive release.zip --checksum SHA256
```

Install only a local ZIP whose SHA-256 you have independently verified:

```bash
adbgath update install --archive release.zip --checksum SHA256
```

Rollback:

```bash
adbgath update rollback
```

The updater rejects path traversal and symlink entries, limits archive entries/decompressed size, validates project metadata, preserves persistent directories, smoke-tests the staged release, and restores the previous installation automatically on failure.

## Workspace

Default location:

```text
~/adbgath-workspace/
```

Typical structure:

```text
adbgath-workspace/
├── adbgath.db
├── apks/
├── backups/
├── bundles/
├── captures/
├── evidence/
├── exports/
├── frida/
│   └── sessions/
├── logs/
├── projects/
├── reports/
├── transactions/
└── uploads/
```

Override it with `--workspace` or `ADBGATH_WORKSPACE`.

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
python -m build
```

CI runs on Windows and Ubuntu with Python 3.11, 3.12, and 3.13. Dedicated workflows smoke-test the complete Windows installer and authorized read-only operations against an Android 15 emulator. Tests cover branding integrity, CLI parsing, strict validation, safe ADB wrapping, transactional replacement, split APKs, static analysis, evidence manifests, projects, jobs, snapshots, reports, authentication, plugins, updater rollback, web security, and cross-platform installer expectations.

## Security documentation

- [`docs/SECURITY.md`](docs/SECURITY.md)
- [`docs/WEB_UI.md`](docs/WEB_UI.md)
- [`docs/WINDOWS.md`](docs/WINDOWS.md)
- [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md)
- [`docs/IMPLEMENTATION_REPORT.md`](docs/IMPLEMENTATION_REPORT.md)

## License

See [`LICENSE`](LICENSE).
