# Security design and threat model

## Intended use

ADB-Gath is intended for authorized Android security assessment, development, incident response, forensic collection, controlled labs, emulators, CTFs, and in-scope bug-bounty testing.

## Host command execution

`AdbClient` executes argument arrays through `subprocess.run()` or `subprocess.Popen()` with `shell=False`. User input is not concatenated into CMD, PowerShell, Bash, or another host shell command.

Validated values include:

- ADB serials.
- Android package names.
- User/profile identifiers.
- Host/port endpoints.
- Remote Android paths.
- Local paths.
- Interfaces, ports, durations, and log formats.

Device-side root packet capture necessarily invokes a controlled `su -c` command. Its interpolated values are restricted by validators and generated paths.

## State-changing operations

Application install, uninstall, replace, and similar operations require explicit device/profile selection. Web operations marked destructive require the literal confirmation value `AUTHORIZED`.

Transactional replacement attempts `install -r` before any uninstall. Uninstall/install fallback is disabled unless explicitly approved, and rollback is attempted from previously pulled APKs when the fallback installation fails.

## Web modes

### Local mode

Default binding is `127.0.0.1`. The application issues a random process-local session cookie and does not require a password.

### Remote mode

Remote mode is disabled unless the operator supplies:

- A non-loopback host.
- A token of at least 24 characters.
- A TLS certificate.
- A TLS private key.

Plaintext remote binding is rejected. Remote login uses constant-time token comparison, secure HTTP-only same-site cookies, HSTS, and per-client login throttling.

Remote mode does not make ADB-Gath a multi-user service. Place it behind a trusted network boundary and use a dedicated host account.

## Browser controls

- No arbitrary shell or arbitrary ADB endpoint.
- Shared action allowlist.
- Strict operation payload schema.
- No permissive CORS.
- Same-origin credentials.
- Content Security Policy.
- Clickjacking protection.
- MIME sniffing protection.
- Restricted referrer and browser permissions.
- WebSocket cookie and Origin checks.
- Workspace-constrained downloads.
- Collision-safe uploads.
- 512 MiB upload limit.
- Generic unexpected-error responses.

## Evidence handling

Text evidence can contain tokens, cookies, identifiers, email addresses, or phone-like values. Redacted copies are produced by default; originals remain available for authorized forensic use. Review redaction results before sharing reports.

Every recorded artifact receives SHA-256 metadata. Set `ADBGATH_MANIFEST_HMAC_KEY` to create an HMAC-SHA256 signature for the manifest. Protect that key outside the evidence directory.

## Static analysis limitations

Static findings are indicators, not automatic proof of exploitability. Binary Android manifests require Android SDK tools for complete decoding. Every finding should be validated on an authorized test device and reviewed for runtime authorization, signature permissions, framework behavior, and intended application design.

## Plugins

Plugins execute Python code with the privileges of the ADB-Gath process. Install plugins only from trusted sources. Plugins must declare permissions, and execution requires explicit approval of all declared permissions.

## Frida scripts

Bundled scripts observe TLS, cryptographic API, and WebView activity. They do not bypass pinning, export keys, steal credentials, or change application behavior. Scripts must be JavaScript, are size-limited, and are syntax-checked with Node.js when it is available. Execution records are stored in SQLite; stdout and stderr files are redacted by default. Operators must deliberately disable redaction when raw local evidence is required.

## Updates

The updater accepts only a local ZIP and explicit SHA-256 for installation. It rejects:

- Checksum mismatches.
- Path traversal.
- Symbolic-link entries.
- Excessive entry count.
- Excessive decompressed size.
- Invalid project/package metadata.

It stages and smoke-tests the release, preserves configured data directories, creates a rollback copy, performs a same-volume swap, and automatically restores the previous tree if post-install validation fails.

## Project exports

Project ZIP exports include database-derived metadata and only regular artifact files that resolve inside the configured workspace. Missing files, symbolic links, duplicate archive names, and external paths are skipped and recorded in `export-manifest.json`. Every included file is rehashed during export.
