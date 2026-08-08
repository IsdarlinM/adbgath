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

**ADB-Gath 3.7.0** is a cross-platform Android assessment and evidence toolkit for authorized mobile-security work. It provides a native Windows/Linux CLI, authenticated multi-workspace Web UI, Android Wireless Debugging, persistent projects, reproducible evidence, static/runtime analysis, secure updates, and an optional mTLS Distributed Lab.

> Use ADB-Gath only on devices, applications, accounts, and environments you own or are explicitly authorized to test.

## What's new in 3.7.0

- First-party Web authentication with `user` and `administrator` roles.
- Isolated per-user Web workspace namespaces.
- Explicit **WORKSPACE** selector and create-workspace button in the main dashboard.
- Existing meaningful 3.6 workspace can be assigned to the first administrator without moving its files.
- Passwords hashed with scrypt using random salts; plaintext passwords are never stored.
- Only SHA-256 hashes of random browser session tokens are stored.
- Session-bound CSRF protection for unsafe Web APIs.
- Authenticated WebSockets with session-expiry enforcement.
- Tenant-aware background jobs that stay bound to the workspace in which they were submitted.
- Fixed Security Audit / MASTG Web job requests returning HTTP 422.
- Structured validation errors are rendered as readable messages instead of `[object Object]`.
- `web-user` and `web-workspace` administration commands.
- Distributed Lab and Advanced Wireless remain integrated inside the main green Web dashboard.

The approved ADB-Gath logo, name, banner and visual identity are preserved.

## Requirements

Required:

- Python 3.11 or newer.
- Android SDK Platform-Tools (`adb`).
- An authorized Android device or emulator for device operations.

Optional components include Java/bundletool, Android static-analysis tools, Frida, and device-side packet capture dependencies.

No platform executables, APKs, JARs or other third-party binaries are committed to the repository.

## Install

Windows:

```bat
installers\windows\install.cmd
```

Linux:

```bash
chmod +x installers/linux/install.sh
./installers/linux/install.sh
```

Then:

```bash
adbgath --version
adbgath doctor --fix
adbgath devices
adbgath web
```

See [`docs/WINDOWS.md`](docs/WINDOWS.md) and [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md) for platform-specific installation details.

## Web authentication and first run

Start the local server:

```bash
adbgath web
```

On the first browser visit, create the first administrator. Passwords must contain at least 12 characters.

Default server identity/workspace registry:

```text
Windows: %LOCALAPPDATA%\adbgath\server
Linux:   ${XDG_DATA_HOME:-~/.local/share}/adbgath-server
```

Override it with `ADBGATH_SERVER_HOME` when required.

The server database is separate from each assessment workspace. See [`docs/WEB_AUTH_3_7.md`](docs/WEB_AUTH_3_7.md) for the authentication, CSRF, session, migration and workspace-isolation model.

## Workspace selector

The Web top bar now separates three concepts:

```text
TARGET DEVICE   -> selected ADB transport/device
PROFILE         -> Android OS user/profile
WORKSPACE       -> ADB-Gath assessment workspace for the logged-in Web user
```

Use **WORKSPACE** to switch between your workspaces. Use the adjacent `+` button to create and select a new one.

Projects, jobs, snapshots, findings, reports, evidence and the workspace SQLite database resolve against the authenticated user's active workspace. Workspace IDs from the browser are checked against their owner before use.

Workspace isolation protects ADB-Gath data. It does not create separate ACLs for physical Android transports visible to the shared ADB server.

## Web users

Administrators receive a **Users** section in the same main dashboard.

Local CLI administration:

```bash
adbgath web-user list
adbgath web-user add analyst --role user
adbgath web-user add backup-admin --role administrator
adbgath web-user reset-password analyst
adbgath web-user disable analyst
adbgath web-user enable analyst

adbgath web-workspace list analyst
adbgath web-workspace create analyst "Android 16 assessment"
```

Passwords are prompted without echo. For automation, use `--password-env ENV_NAME` rather than putting a password in command history.

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

Both Web actions are long-running, workspace-scoped jobs in 3.7.0. Regression tests cover both request contracts and job completion.

## Wireless Debugging

The main Web **Wireless** view supports:

- QR pairing without manually typing a pairing code;
- six-digit Android pairing-code workflow;
- mDNS discovery;
- connect/auto-connect;
- diagnostics and repair;
- known targets and aliases;
- live wireless broker/watch.

CLI examples:

```bash
adbgath wireless qr
adbgath wireless discover
adbgath wireless pair 192.168.1.50:37123
adbgath wireless connect 192.168.1.50:41267
adbgath wireless auto-connect
adbgath wireless diagnose
```

Pairing and connection ports normally differ. See [`docs/WIRELESS.md`](docs/WIRELESS.md).

## Projects and evidence

```bash
adbgath project create "Authorized Android Assessment" --scope "owned test device"
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
```

## Distributed Lab

Distributed Lab remains optional and integrated into the main Web navigation. It uses mTLS, enrolled outbound-only agents, RBAC, policy-controlled jobs, content-addressed evidence and tamper-evident audit history.

See [`docs/DISTRIBUTED_LAB.md`](docs/DISTRIBUTED_LAB.md) and [`docs/SECURITY_3_6.md`](docs/SECURITY_3_6.md).

## Secure update

```bash
adbgath update
adbgath update force
adbgath update check
adbgath update rollback
```

`update force` is useful for reinstalling a hotfix or repairing the managed package. User/workspace data is outside the package replacement path.

## Uninstall

Preserve workspaces and Web user data:

Windows:

```bat
installers\windows\uninstall.cmd -KeepWorkspace
```

Linux:

```bash
./installers/linux/uninstall.sh --keep-workspace
```

A full uninstall removes the default 3.7 server registry. A custom `ADBGATH_SERVER_HOME` is preserved for explicit operator review.

## Security model

ADB-Gath uses:

- allowlisted operations rather than an arbitrary browser shell;
- `shell=False` argument-array process execution;
- semantic ADB failure detection;
- bounded asynchronous process output/cancellation;
- per-user Web authentication and workspace ownership checks;
- scrypt password hashing;
- hashed session tokens at rest;
- CSRF protection and same-origin authentication forms;
- authenticated WebSockets with session expiration;
- TLS-only non-loopback Web mode;
- role-gated Web administration;
- mTLS distributed agents;
- RBAC and explicit approval for destructive distributed operations;
- tamper-evident audit history;
- SHA-256/content-addressed evidence;
- Ed25519 plugin signatures;
- validated updater staging and rollback.

## Development

```bash
python -m pytest -q
python -m compileall -q src
node --check src/adbgath/web/static/app.js
node --check src/adbgath/web/static/app370.js
```

The suite includes FakeADB regressions plus focused authentication, CSRF, workspace ownership, user authorization, Security/MASTG jobs, Wireless Debugging, CAS, audit, RBAC, mTLS lab and updater tests.

## Documentation

- [`docs/WEB_AUTH_3_7.md`](docs/WEB_AUTH_3_7.md)
- [`docs/WEB_UI.md`](docs/WEB_UI.md)
- [`docs/WIRELESS.md`](docs/WIRELESS.md)
- [`docs/DISTRIBUTED_LAB.md`](docs/DISTRIBUTED_LAB.md)
- [`docs/SUPPLY_CHAIN.md`](docs/SUPPLY_CHAIN.md)
- [`docs/WINDOWS.md`](docs/WINDOWS.md)

## License

See [`LICENSE`](LICENSE).
