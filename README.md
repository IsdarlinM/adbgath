# adbgath

```text
╭──────────────────────────────────────────────────────────────────────────────╮
│  ADB-GATH  ::  Defensive Android Assessment Toolkit  ::  v3.0.0             │
│  Cross-platform CLI + local security-focused web workspace                  │
╰──────────────────────────────────────────────────────────────────────────────╯
```

**adbgath** is a cross-platform defensive Android assessment toolkit for authorized mobile testing. Version 3 replaces the Linux-only Bash core with a Python service layer that runs natively on Windows and Linux, while preserving the main ADB workflows and exposing the same capabilities through a professional local web interface.

The project does not include prebuilt executables or Android binaries. The installers create the Python environment, install dependencies, download official Android SDK Platform-Tools when needed, generate launchers, and configure the user `PATH`.

## Highlights

- Native Windows and Linux CLI with the global `adbgath` command.
- Local web workspace with device selection, user/profile selection, structured command forms, live logcat, package inventory, audit findings, uploads, and artifact downloads.
- Shared execution layer: CLI and web UI call the same validated Python services.
- Safe subprocess execution: no `shell=True`, no browser-accessible arbitrary terminal, and allowlisted web actions.
- USB and wireless debugging support.
- APK download, install, uninstall, replacement, and local static metadata/hash checks.
- Device, user/profile, package, runtime, network, proxy, and content-provider inspection.
- Timed and live logcat workflows with package, PID, format, and regular-expression filtering.
- Rooted-device `tcpdump` capture support.
- Optional Frida integration.
- JSON and Markdown posture reports plus OWASP MASTG-oriented evidence bundles.
- Windows/Linux CI matrix and fake-ADB automated tests.

## Requirements

The installers handle the required host dependencies:

- Python 3.11 or newer.
- Android SDK Platform-Tools (`adb`).
- Python web dependencies.
- Optional Frida tools unless installation is explicitly skipped.

Device requirements:

- Android device or emulator with USB Debugging or Wireless Debugging enabled.
- User approval of the ADB RSA prompt.
- Root or a working `su` command only for packet capture.
- `tcpdump` on the device, or a compatible binary supplied with `sniff push-tcpdump`.

## Windows installation

Open **Command Prompt** or **Windows Terminal** in the repository directory and run:

```bat
installers\windows\install.cmd
```

The installer:

1. Detects Python 3.11+.
2. Installs Python 3.12 for the current user through WinGet, with an official Python installer fallback.
3. Creates an isolated virtual environment under `%LOCALAPPDATA%\Programs\adbgath`.
4. Installs adbgath, FastAPI/Uvicorn, upload support, and Frida tools.
5. Downloads the official latest Android SDK Platform-Tools archive from Google.
6. Generates `adbgath.cmd` and `adbgath-web.cmd` launchers.
7. Adds the launcher and Platform-Tools directories to the user `PATH`.
8. Sets `ADB_PATH` and `ADBGATH_HOME` for the current user.
9. Validates both `adbgath` and `adb`.

Open a new terminal after installation:

```bat
adbgath --version
adbgath doctor
adbgath devices
adbgath web
```

Optional installer switches:

```bat
installers\windows\install.cmd -SkipFrida
installers\windows\install.cmd -SkipPlatformTools
installers\windows\install.cmd -Force
```

Uninstall:

```bat
installers\windows\uninstall.cmd
```

Preserve the workspace during uninstall:

```bat
installers\windows\uninstall.cmd -KeepWorkspace
```

See [Windows installation details](docs/WINDOWS.md) and the [quick start](docs/QUICKSTART.md).

## Linux installation

```bash
chmod +x installers/linux/install.sh
./installers/linux/install.sh
```

The installer detects `apt`, `dnf`, `pacman`, or `zypper`, installs Python/venv/ADB when missing, creates an isolated environment, installs the package, and adds `$HOME/.local/bin` to common shell startup files.

```bash
adbgath doctor
adbgath devices
adbgath web
```

Skip optional Frida tooling:

```bash
./installers/linux/install.sh --skip-frida
```

## Web interface

Start the web workspace:

```bash
adbgath web
```

Default address:

```text
http://127.0.0.1:8765
```

Use a custom local port:

```bash
adbgath web --port 9000
```

The server binds to loopback by default. Remote network binding is intentionally rejected; use the UI only from the host running adbgath. The UI uses a same-site local session cookie, restrictive response headers, allowlisted actions, path confinement for artifact downloads, upload size limits, and explicit confirmation for state-changing operations.

Web capabilities include:

- Device and Android profile selectors.
- Dependency and environment status.
- Complete allowlisted operation builder.
- Installed package explorer.
- Secure local file staging for APKs, Frida scripts, and device-side tools.
- Live WebSocket logcat stream.
- Security audit findings and severity summary.
- MASTG-oriented evidence collection.
- Download links for generated workspace artifacts.

See [Web UI architecture and security](docs/WEB_UI.md).

## CLI overview

```bash
adbgath -h
adbgath <command> -h
```

Global options:

```text
--device, -D, -s SERIAL   Select an ADB device
--user, -u PROFILE        Select Android profile: ID, current, owner
--adb-path PATH           Override adb/adb.exe discovery
--workspace PATH          Override the artifact workspace
--json                    Emit JSON
--no-banner               Suppress the banner
```

### Devices and wireless debugging

```bash
adbgath devices
adbgath connect 192.168.1.50:5555
adbgath disconnect 192.168.1.50:5555
```

Android 11+ may require pairing first:

```bash
adb pair 192.168.1.50:37123
adbgath connect 192.168.1.50:5555
```

### Users, packages, and APK paths

```bash
adbgath --device emulator-5554 list users
adbgath --device emulator-5554 --user current list packages
adbgath --device emulator-5554 list packages --include-paths
adbgath --device emulator-5554 list packages --system third-party
adbgath --device emulator-5554 list paths --package com.example.app
```

### Download APKs

Download APKs for all packages visible to the selected profile:

```bash
adbgath --device emulator-5554 --user current download --output ./apk-backup
```

Download selected packages:

```bash
adbgath --device emulator-5554 download com.example.one com.example.two
```

Download known remote APK paths:

```bash
adbgath --device emulator-5554 download /data/app/~~.../base.apk
```

### Install, uninstall, and replace

App-changing commands require an explicit Android profile.

```bash
adbgath --device emulator-5554 --user 0 install app.apk
adbgath --device emulator-5554 --user current install app.apk --replace
adbgath --device emulator-5554 --user 10 uninstall com.example.app
adbgath --device emulator-5554 --user 0 replace com.example.app replacement.apk
```

### Device and application information

```bash
adbgath --device emulator-5554 info basic
adbgath --device emulator-5554 info network
adbgath --device emulator-5554 info security
adbgath --device emulator-5554 info all
adbgath --device emulator-5554 app com.example.app
```

### Runtime inspection

```bash
adbgath --device emulator-5554 runtime summary --package com.example.app
adbgath --device emulator-5554 runtime processes
adbgath --device emulator-5554 runtime activities
adbgath --device emulator-5554 runtime services
```

### Logcat

Live stream:

```bash
adbgath --device emulator-5554 logs listen
adbgath --device emulator-5554 logs listen --package com.example.app
adbgath --device emulator-5554 logs listen --regex "token|password|exception"
```

Timed capture:

```bash
adbgath --device emulator-5554 logs capture --duration 60 --output ./logs/app.log
adbgath --device emulator-5554 logs capture --package com.example.app --clear-first
```

Clear the buffer:

```bash
adbgath --device emulator-5554 logs clear
```

### Rooted network capture

```bash
adbgath --device emulator-5554 sniff interfaces
adbgath --device emulator-5554 sniff push-tcpdump --file ./tcpdump
adbgath --device emulator-5554 sniff capture --interface wlan0 --duration 60
```

Packet capture uses `su` and a device-side `tcpdump`; it is not attempted on non-rooted devices.

### Proxy and port mappings

```bash
adbgath --device emulator-5554 proxy show
adbgath --device emulator-5554 proxy set 127.0.0.1:8080
adbgath --device emulator-5554 proxy clear
adbgath --device emulator-5554 forward reverse 8080 8080
```

### Static analysis, Frida, content providers, and backups

```bash
adbgath static ./app.apk
adbgath --device emulator-5554 content --package com.example.app
adbgath --device emulator-5554 frida ps
adbgath --device emulator-5554 frida attach --package com.example.app --script ./trace.js
adbgath --device emulator-5554 backup com.example.debuggable --output ./backup.tar
```

Static analysis always produces SHA-256 and file metadata. Additional manifest/package metadata is collected when `apkanalyzer`, `aapt`, or `aapt2` is available.

### Inventory, audits, and evidence collection

```bash
adbgath --device emulator-5554 inventory --output ./inventory.json
adbgath --device emulator-5554 security --output ./security.json
adbgath --device emulator-5554 collect --output ./device-collection
adbgath --device emulator-5554 mastg --output ./mastg-evidence
```

The security command checks a small defensive posture baseline and writes JSON plus Markdown. It is not an automated compliance certification and does not replace manual OWASP MASTG testing.

## Legacy v2 flag compatibility

Common Bash-era flags are translated when no explicit v3 subcommand is present:

```bash
adbgath --devices
adbgath --device emulator-5554 -l users
adbgath --device emulator-5554 -i network
adbgath --device emulator-5554 --user 0 -I app.apk
adbgath --device emulator-5554 --user 0 -U com.example.app
adbgath --device emulator-5554 -C --output ./collection
```

The root `adbgath.sh` file remains as a Linux compatibility launcher after installation. Legacy batch inputs are also preserved:

```bash
adbgath --device SERIAL --user current download --file examples/packages.txt
adbgath --device SERIAL --user 0 install --file examples/apks.txt
adbgath --device SERIAL --user 0 uninstall --file examples/packages.txt
adbgath --device SERIAL --user 0 replace --file examples/replacements.txt
```

Replacement files use `APK_FILE PACKAGE_NAME`; quoted APK paths may contain spaces.

## Configuration

Environment variables:

```text
ADB_PATH             Explicit path to adb/adb.exe
ADBGATH_HOME         Installation root used by platform-specific discovery
ADBGATH_WORKSPACE    Default report and artifact workspace
```

Default workspace:

- Windows: `%USERPROFILE%\adbgath-workspace`
- Linux: `$HOME/adbgath-workspace`

## Security model

- Every external command uses an argument array and `shell=False`.
- Device serials, package names, profile IDs, paths, interfaces, ports, and durations are validated.
- The web API exposes an action allowlist rather than a shell or raw ADB endpoint.
- State-changing web operations require the literal confirmation `AUTHORIZED`.
- The server only accepts loopback binding.
- Artifact downloads are confined to the configured workspace.
- Uploaded filenames are normalized and uploads are capped at 512 MiB.
- The project intentionally does not automate credential theft, persistence, evasion, or unauthorized access.

See [Security design](docs/SECURITY.md) and the [implementation report](docs/IMPLEMENTATION_REPORT.md).

## Development

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

python -m pip install -e ".[dev,full]"
python -m pytest
python -m ruff check src tests
python -m adbgath.cli --version
```

Cross-platform CI tests Python 3.11, 3.12, and 3.13 on Windows and Ubuntu.

## Project structure

```text
adbgath/
├── src/adbgath/
│   ├── adb.py                 Safe ADB subprocess wrapper
│   ├── service.py             Shared CLI/web capabilities
│   ├── cli.py                 Cross-platform command-line interface
│   ├── webapp.py              FastAPI local web service
│   ├── validation.py          Input and path validation
│   └── web/static/            Professional HTML/CSS/JavaScript UI
├── installers/
│   ├── windows/               CMD + PowerShell installer/uninstaller
│   └── linux/                 Linux installer/uninstaller
├── examples/                  Batch input examples
├── tests/                     Fake-ADB unit and web tests
├── docs/                      Windows, web, security, and migration guides
└── .github/workflows/ci.yml   Windows/Linux CI matrix
```

## Responsible use

Use adbgath only on devices, applications, emulators, laboratories, CTFs, or bug-bounty targets for which you have explicit authorization. Device state changes, packet capture, instrumentation, and app-data collection may affect privacy and stability.

## License

MIT License. See [LICENSE](LICENSE).
