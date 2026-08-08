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
Developer: IsdarlinM | Version: 3.7.0
Threat intel • Device forensics • Defensive ADB workflow
```

**ADB-Gath 3.7.0** is a cross-platform Android assessment, evidence, and optional distributed-lab workspace for authorized security testing. It provides a native Windows/Linux CLI, an authenticated multi-workspace Web UI, Android Wireless Debugging, persistent projects, reproducible evidence, static/runtime analysis, secure updates, and an optional mTLS distributed lab.

> Use ADB-Gath only on devices, applications, accounts, and environments you own or are explicitly authorized to test.

## 3.7.0 highlights

- Adds first-party Web user authentication with `user` and `administrator` server roles.
- Adds isolated per-user Web workspaces with an explicit workspace selector in the main top bar.
- Migrates an existing meaningful 3.6 workspace to the first administrator without moving its files.
- Stores passwords using scrypt with random salts; plaintext passwords are never stored.
- Stores only SHA-256 hashes of browser session tokens and revokes sessions after password reset/disable.
- Adds session-bound CSRF protection to unsafe Web API requests while preserving existing Wireless/Lab modules.
- Makes background jobs workspace-aware so users and concurrent requests cannot cross workspace boundaries.
- Fixes Security Audit and MASTG Web job submission returning HTTP 422.
- Renders structured validation failures as readable text instead of `[object Object]`.
- Adds `web-user` and `web-workspace` administration commands.
- Preserves all 3.6 features: bounded async processes, content-addressed evidence, RBAC/audit, Ed25519 plugins, SBOMs, integrated Distributed Lab, QR/code pairing, and the unified green Web theme.

The original logo, banner, name, and visual identity are preserved.

## Architecture

```text
Windows CLI ───────────┐
Linux CLI ─────────────┼── Shared operation catalog ── AdbgathService ── AdbClient ── adb/adb.exe
Authenticated Web UI ──┤              │
Per-user Web jobs ─────┘              ├── User/workspace context
                                      ├── Wireless broker / QR coordinator
                                      ├── Async process supervisor
                                      ├── Projects / SQLite / CAS evidence
                                      ├── RBAC / audit / signed plugins
                                      ├── Optional mTLS lab controller + outbound agents
                                      └── APK / Bundle / static-runtime correlation
```

The browser has no arbitrary shell endpoint and no raw arbitrary ADB command endpoint.

## Requirements

Required:

- Python 3.11 or newer.
- Android SDK Platform-Tools (`adb`).
- An authorized Android device or emulator for device operations.

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

The installer manages its Python environment and Platform-Tools and configures the command path. See [`docs/WINDOWS.md`](docs/WINDOWS.md).

Portable mode:

```bat
installers\windows\portable.cmd
```

## Linux installation

```bash
chmod +x installers/linux/install.sh
./installers/linux/install.sh
```

Portable mode:

```bash
./installers/linux/portable.sh ./portable-adbgath
```

## Web authentication: first run

Start the server:

```bash
adbgath web
```

On the first browser visit, ADB-Gath asks you to create the first administrator. Passwords must contain at least 12 characters.

If an existing 3.6 workspace is detected, the setup page identifies it and assigns it to the first administrator without relocating the workspace.

After setup, the dashboard requires username/password authentication.

Default server identity/workspace-registry locations:

```text
Windows: %LOCALAPPDATA%\adbgath\server
Linux:   ${XDG_DATA_HOME:-~/.local/share}/adbgath/server
```

Override with:

```text
ADBGATH_SERVER_HOME
```

See [`docs/WEB_AUTH_3_7.md`](docs/WEB_AUTH_3_7.md).

## Web workspace selector

The main top bar now contains separate concepts:

```text
TARGET DEVICE   -> selected ADB device
PROFILE         -> Android user/profile (current, 0, work profile, ...)
WORKSPACE       -> ADB-Gath assessment workspace for the logged-in Web user
```

Use the **WORKSPACE** dropdown to switch. Use `+` to create a new isolated workspace.

Each new Web user receives a separate default workspace namespace. Jobs, projects, snapshots, findings, reports and workspace database records resolve against the authenticated user's active workspace.

## Web user administration

Administrators receive a **Users** section inside the same dashboard shell.

Local CLI administration:

```bash
adbgath web-user list
adbgath web-user add analyst --role user
adbgath web-user add backup-admin --role administrator
adbgath web-user reset-password analyst
adbgath web-user disable analyst
adbgath web-user enable analyst
```

Do not place passwords directly on a command line. Prompt securely, or use a short-lived environment variable:

```bash
ADBGATH_NEW_PASSWORD='replace-this-secret' \
  adbgath web-user add analyst --role user --password-env ADBGATH_NEW_PASSWORD
```

Workspaces can also be prepared administratively:

```bash
adbgath web-workspace list analyst
adbgath web-workspace create analyst "Android 16 assessment"
```

## Remote Web mode

Local loopback remains the default. Non-loopback mode requires the existing remote startup guard plus TLS:

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token 'use-a-long-startup-secret-here' \
  --tls-cert ./server-cert.pem \
  --tls-key ./server-key.pem
```

Web users still authenticate with individual accounts after the server starts. Do not expose ADB-Gath directly to the public Internet.

## Wireless Debugging

### QR pairing

On Android open **Developer options → Wireless debugging → Pair device with QR code**. In the main Web UI select **Wireless → QR pairing**, or use:

```bash
adbgath wireless qr
```

Useful options:

```bash
adbgath wireless qr --timeout 180
adbgath wireless qr --no-auto-connect
adbgath wireless qr --output ./pairing.svg --open
```

QR secrets remain ephemeral and are excluded from command arguments, SQLite jobs, reports and browser storage.

### Six-digit pairing code

On Android select **Pair device with pairing code**:

```bash
adbgath wireless discover
adbgath wireless pair 192.168.1.50:37123
```

Then connect using the separate connection endpoint shown by Android:

```bash
adbgath wireless connect 192.168.1.50:41267
```

The pairing and connection ports normally differ.

Additional operations:

```bash
adbgath wireless status
adbgath wireless diagnose
adbgath wireless diagnose --fix
adbgath wireless known
adbgath wireless auto-connect
adbgath wireless watch
```

Advanced Wireless controls remain integrated inside the main dashboard. See [`docs/WIRELESS.md`](docs/WIRELESS.md).

## Security Audit and MASTG

CLI:

```bash
adbgath --device SERIAL security
adbgath --device SERIAL mastg
```

Web:

```text
Security Audit
  -> Run audit
  -> Build MASTG bundle
```

Both Web buttons queue workspace-scoped background jobs. ADB-Gath 3.7 includes a regression test for both job contracts.

## Projects and evidence

Typical commands:

```bash
adbgath project create "Authorized Android Assessment" --scope "owned test device"
adbgath project list
adbgath evidence --package com.example.app
adbgath snapshot create before --package com.example.app
adbgath security
adbgath report PROJECT_ID --format html
```

Content-addressed evidence:

```bash
adbgath artifact-store status
adbgath artifact-store import --path evidence.log --project-id PROJECT
adbgath artifact-store verify
adbgath artifact-store gc
adbgath artifact-store gc --apply
```

## Distributed Lab

Distributed Lab is integrated into the main Web navigation and is optional. The controller uses mTLS and enrolled outbound-only agents.

```bash
adbgath lab pki-init --dir ./lab-pki
adbgath lab controller-cert --dir ./lab-pki --host 127.0.0.1
adbgath lab agent-enroll lab-windows-01 --pki-dir ./lab-pki --controller https://127.0.0.1:9443
```

Start controller:

```bash
adbgath lab controller \
  --host 127.0.0.1 --port 9443 \
  --cert ./lab-pki/controller-adbgath-controller-cert.pem \
  --key ./lab-pki/controller-adbgath-controller-key.pem \
  --ca ./lab-pki/ca-cert.pem
```

See [`docs/DISTRIBUTED_LAB.md`](docs/DISTRIBUTED_LAB.md).

## Secure update

Normal update:

```bash
adbgath update
```

Force reinstall the current latest revision, useful after a hotfix or damaged installation:

```bash
adbgath update force
```

Advanced/manual modes remain available:

```bash
adbgath update check
adbgath update plan
adbgath update install --archive FILE.zip --checksum SHA256
adbgath update rollback
```

Update preserves managed configuration and workspace/server data.

## Uninstall

Windows, preserve workspace/user data:

```bat
installers\windows\uninstall.cmd -KeepWorkspace
```

Windows full data removal:

```bat
installers\windows\uninstall.cmd
```

Linux preserve workspace/user data:

```bash
./installers/linux/uninstall.sh --keep-workspace
```

If `ADBGATH_SERVER_HOME` points to a custom location, review that directory explicitly before deleting it.

## Security properties

ADB-Gath intentionally uses:

- allowlisted operations rather than arbitrary browser shell execution;
- argument-array subprocesses with `shell=False`;
- semantic ADB failure detection;
- bounded process output and cancellation;
- authenticated Web sessions and per-user workspace ownership checks;
- CSRF protection on unsafe Web API requests;
- WebSocket session checks;
- TLS-only non-loopback Web mode;
- scrypt password hashing;
- session-token hashes at rest;
- mTLS for distributed agents;
- RBAC and explicit approval for destructive distributed operations;
- tamper-evident audit history;
- SHA-256 evidence and content-addressed artifacts;
- Ed25519 plugin signatures;
- updater archive/checksum validation and rollback.

## Development and validation

```bash
python -m pytest -q
python -m compileall -q src
```

JavaScript syntax can be checked with Node when installed:

```bash
node --check src/adbgath/web/static/app.js
node --check src/adbgath/web/static/app370.js
```

The test suite includes FakeADB device regressions and focused tests for authentication, CSRF, workspace ownership, jobs, Wireless Debugging, CAS, RBAC, audit, mTLS lab workflows and update behavior.

## Documentation

- [`docs/WEB_AUTH_3_7.md`](docs/WEB_AUTH_3_7.md) — Web users, sessions, workspaces and migration.
- [`docs/WEB_UI.md`](docs/WEB_UI.md) — Web workspace behavior.
- [`docs/WIRELESS.md`](docs/WIRELESS.md) — Wireless Debugging.
- [`docs/DISTRIBUTED_LAB.md`](docs/DISTRIBUTED_LAB.md) — optional distributed lab.
- [`docs/SECURITY_3_6.md`](docs/SECURITY_3_6.md) — 3.6 security foundations retained by 3.7.
- [`docs/SUPPLY_CHAIN.md`](docs/SUPPLY_CHAIN.md) — SBOM/provenance.
- [`docs/WINDOWS.md`](docs/WINDOWS.md) — Windows installation/repair.

## License

See [`LICENSE`](LICENSE).
