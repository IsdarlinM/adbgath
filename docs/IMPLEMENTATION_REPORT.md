# ADB-Gath 3.2.9 implementation report

## Objective

Version 3.2.9 completes the migration from a Linux/Bash-only utility to a cross-platform Android security assessment workspace. The release keeps the historical ADB-Gath identity while providing native Windows/Linux operation, a shared CLI/Web capability layer, persistent assessment data, reproducible evidence, and safer application-management workflows.

## Architecture

```text
CLI / Interactive mode ─┐
Web UI / Background jobs├── Operation catalog ── AdbgathService ── AdbClient
Plugin entry points ────┘          │                 │
                                   │                 └── adb/adb.exe
                                   ├── SQLite project store
                                   ├── Evidence and reports
                                   ├── Rules and APK analysis
                                   └── Update/rollback manager
```

Key design decisions:

- Python 3.11+ provides a native common core on Windows and Linux.
- All ADB commands use argument arrays and `shell=False`.
- The browser can invoke only catalogued operations.
- CLI forms, web forms, validation metadata, destructive flags, long-running flags, requirements, and platform metadata originate from one catalog.
- Persistent state uses SQLite with WAL and foreign keys.
- Artifacts remain ordinary files in a user-controlled workspace.

## Completed roadmap

### Application lifecycle

- Single and multi-APK installation.
- Split APK directory and `.apks` discovery.
- APK-set validation using available Android build tools.
- Transactional replacement:
  - pull current base/split APKs;
  - attempt in-place `install -r` first;
  - preserve the installed application if that fails;
  - use uninstall/install only with explicit approval;
  - attempt automatic rollback if fallback installation fails.

### Static assessment

The APK inspector records hashes, archive structure, manifest attributes, exported components, implicit exports, permissions, deep links, backup configuration, cleartext configuration, Network Security Configuration references, task affinity, launch modes, signing schemes, native ABIs, endpoints, embedded-secret indicators, and WebView indicators.

It applies defensive rules and generates structured findings with severity, confidence, evidence, impact, safe validation guidance, false-positive conditions, remediation, and references.

### Persistent workspace

SQLite-backed entities:

- Projects.
- Sessions.
- Findings and workflow states.
- Evidence artifacts and hashes.
- Background jobs.
- Snapshots.
- Device groups.
- Frida observation sessions and redacted log references.

### Evidence

The evidence collector can capture:

- Device/build metadata.
- Users, package inventory, runtime state, and capabilities.
- Logcat, properties, activities, windows, and package dumps.
- Screenshot and optional screen recording.
- Android bugreport.
- Base/split APKs.
- Per-artifact SHA-256.
- Command, result, duration, device, ADB version, and tool version.
- Redacted copies of text evidence.
- Optional HMAC-SHA256 manifest signature.

### Reports

Supported formats:

- JSON.
- Markdown.
- Self-contained HTML.
- CSV.
- SARIF 2.1.0.
- PDF.

Project reports include project metadata, scope, sessions, findings, and artifact records.

### Web UI

The browser workspace includes:

- Dynamic operation forms from the shared catalog.
- Device/profile selection.
- Projects, sessions, jobs, findings, snapshots, and artifact views.
- Background execution with progress and cancellation state.
- Live WebSocket logcat.
- Upload and download confinement.
- Multi-file staging, saved local presets, package pagination, bounded log rendering, bookmarks, local log export, and severity visualization.
- Project ZIP export containing metadata and only workspace-confined artifact files.
- Destructive-action confirmation.
- Local loopback mode by default.
- Optional TLS-only remote mode with a long operator token and login throttling.

### Extensibility

- Built-in rule engine.
- Python entry-point plugin discovery.
- Declared plugin permissions.
- Explicit operator approval before execution.
- Observation-only bundled Frida scripts with version metadata, JavaScript validation, redacted-at-rest logs, and persistent execution history.

### Distribution

Windows installer:

- Detects or installs Python 3.11+.
- Creates an isolated virtual environment.
- Installs Python dependencies and optional Frida.
- Downloads Android Platform-Tools.
- Installs optional Java/bundletool support.
- Creates CMD launchers.
- Configures user `PATH`, `ADB_PATH`, `ADBGATH_HOME`, and `BUNDLETOOL_JAR`.
- Supports repair, force, proxy, offline cache, portable mode, and uninstall.

Linux installer:

- Supports common package managers.
- Creates an isolated environment and launchers.
- Supports optional Frida and bundletool.
- Supports proxy, offline cache, force, portable mode, and uninstall.

No platform binaries are committed to the repository.

## Security boundaries

- No `shell=True` for host execution.
- No browser terminal or arbitrary command endpoint.
- Strict payload fields and types.
- Input validation for packages, serials, profiles, ports, interfaces, paths, durations, and remote endpoints.
- Workspace-constrained artifact downloads.
- Collision-safe uploads and generated files.
- Upload size limit.
- Security headers and same-site HTTP-only cookies.
- TLS required for non-loopback mode.
- ZIP path, symlink, entry-count, and decompressed-size protections in the updater.
- Plugin permissions and destructive confirmations.

## Validation

The source tree includes automated tests for:

- CLI and legacy argument compatibility.
- Branding integrity.
- Safe ADB wrapper behavior.
- Cross-platform path behavior.
- Transactional replacement and rollback.
- Split APK installation.
- Static manifest analysis.
- Evidence manifests and HMAC signatures.
- Project/session/artifact storage.
- Snapshot differences.
- Job persistence.
- Report generation, including PDF.
- Web authentication and operation allowlisting.
- Plugin permission enforcement.
- Secure update, preservation, rollback, checksum rejection, and symlink rejection.
- Installer expectations and absence of committed binaries.
- Frida history/redaction, project ZIP integrity, numeric catalog bounds, and frontend completion controls.

The repository also contains dedicated Windows installer and Android emulator integration workflows.

See the repository CI workflow for the Windows/Ubuntu Python matrix and package build checks.
