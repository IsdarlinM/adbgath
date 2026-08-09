# ADB-Gath 3.7 Web authentication and workspaces

ADB-Gath 3.7.0 adds first-party Web users and strict per-user workspace isolation to the local/remote Web server.

## First run

Start the Web UI normally:

```bash
adbgath web
```

The first browser visit shows a setup form instead of the assessment dashboard. Create the first administrator with a username and a password of at least 12 characters.

If ADB-Gath detects an existing 3.6 workspace, that workspace is assigned to the first administrator without moving its files. Existing projects, reports, artifacts and the workspace database remain in place.

After setup, every Web request requires an authenticated session.

### Remote first-run bootstrap

Non-loopback Web mode always requires a startup token of at least 24 characters. TLS certificate files are optional.

Secure default, with automatic TLS generation:

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token 'LONG_STARTUP_TOKEN'
```

When `--tls-cert` and `--tls-key` are omitted, ADB-Gath creates a persistent-location self-signed ECDSA P-256 server certificate and PKCS#8 private key under the server TLS directory. The certificate uses SHA-256, Server Authentication EKU and Subject Alternative Names for loopback plus locally discoverable hostnames/IP addresses.

If clients connect through a specific IP address or DNS name, add it explicitly to the generated certificate:

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token 'LONG_STARTUP_TOKEN' \
  --tls-san 192.168.1.20 \
  --tls-san adb-lab.example.test
```

Choose the generated-material directory when required:

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token 'LONG_STARTUP_TOKEN' \
  --tls-dir /secure/adbgath/tls
```

ADB-Gath prints the certificate path, private-key path and SHA-256 certificate fingerprint. The generated certificate is self-signed, so browsers and API clients will still show a trust warning until the operator explicitly trusts that certificate or deploys a certificate signed by a trusted CA.

To use an existing certificate:

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token 'LONG_STARTUP_TOKEN' \
  --tls-cert ./server-cert.pem \
  --tls-key ./server-key.pem
```

ADB-Gath validates that the PEM certificate and private key exist, match each other and are inside their validity period before starting Uvicorn.

Plain HTTP is available only through an explicit opt-in:

```bash
adbgath web \
  --host 0.0.0.0 \
  --remote-token 'LONG_STARTUP_TOKEN' \
  --insecure-http
```

`--insecure-http` removes transport encryption. The startup token, login credentials, session cookies and assessment data can be intercepted by anyone able to observe or modify the network path. Use it only on a trusted isolated network, a local lab, or behind another trusted TLS terminator/reverse proxy. It cannot be combined with `--tls-cert`/`--tls-key`.

When no Web users exist yet, the remote setup form requires the startup token in addition to the new administrator username/password. A remote client cannot claim the first administrator without knowing the configured startup token. Failed startup-token attempts are rate-limited per client.

The startup token is not stored as a Web-user password and does not replace individual accounts. Once first-run setup is complete, operators authenticate with their own ADB-Gath Web usernames/passwords.

Local loopback first-run setup does not require the additional startup-token field.

## Authentication model

- Passwords are never stored in plaintext.
- Password verification uses `hashlib.scrypt` with a random 16-byte salt (`N=2^15`, `r=8`, `p=3`, 32-byte output), one of the equivalent scrypt profiles listed by OWASP.
- Browser session tokens are generated with `secrets.token_urlsafe(48)`.
- Only SHA-256 hashes of session tokens are stored in the server database.
- Sessions expire after 12 hours and are revoked on password reset or user disable.
- Cookies are `HttpOnly`, `SameSite=Strict`, and `Secure` when TLS is enabled.
- Unsafe same-origin API requests require an `X-ADBGATH-CSRF` token bound to the authenticated session.
- The CSRF HMAC key remains server-only; browser compatibility cookies contain only a one-way derived marker.
- Authentication setup/login forms validate same-origin `Origin`/`Referer` metadata when a browser provides it.
- WebSocket endpoints resolve the authenticated user before binding an ADB-Gath workspace and long-lived sockets cannot outlive the authenticated session.
- Non-loopback Web mode requires the remote startup token; HTTPS is the default through supplied or automatically generated TLS material.
- Plain remote HTTP is possible only through the explicit `--insecure-http` opt-in.

The server-level identity registry is independent from assessment databases. Default locations are:

```text
Windows: %LOCALAPPDATA%\adbgath\server
Linux:   ${XDG_DATA_HOME:-~/.local/share}/adbgath-server
```

Override the server registry location with `ADBGATH_SERVER_HOME` when required.

On POSIX systems ADB-Gath restricts the default registry/workspace directories and secret/database files to the service account where supported. Automatically generated private TLS keys are written with mode `0600` and the TLS directory with mode `0700` on POSIX systems.

## Workspaces

The top bar now contains an explicit **WORKSPACE** selector. The neighboring `+` button creates another workspace and selects it immediately.

`PROFILE` remains the Android user/profile selector. It is not the ADB-Gath filesystem workspace.

New workspaces are generated inside the authenticated user's namespace:

```text
server/
  users/
    usr_.../
      workspaces/
        ws_.../
          adbgath.db
          ...artifacts and reports...
```

Workspace IDs are random internal identifiers. Browser-supplied workspace IDs are always checked against the authenticated owner before selection. A user cannot select, enumerate jobs from, or access another user's workspace through the Web API.

Background jobs capture the resolved `AdbgathService` for the active workspace before entering the worker thread. A later workspace switch or concurrent request from another user cannot retarget an already queued job.

User/workspace creation uses serialized SQLite transactions. Duplicate user/workspace requests do not leave orphan workspace directories, and concurrent first-run setup attempts cannot create multiple initial administrators.

Expired sessions are rejected and revoked before workspace-selection metadata can be mutated.

Workspace isolation protects ADB-Gath data boundaries. It does not create per-user ACLs for the physical Android transports visible to the shared ADB server.

## User administration

Administrators receive a **Users** view in the main dashboard. It can:

- list Web users;
- create a user or another administrator;
- enable/disable users.

Web-only administrative operations are authorized from the authenticated server role. Browser-supplied Distributed Lab role claims cannot elevate a normal Web user to administrator authority.

Password resets are available from the local CLI so administrators can avoid putting a new password in browser history or browser storage:

```bash
adbgath web-user list
adbgath web-user add analyst --role user
adbgath web-user add backup-admin --role administrator
adbgath web-user reset-password analyst
adbgath web-user disable analyst
adbgath web-user enable analyst
```

For automation, read the password from a short-lived environment variable rather than a command-line argument:

```bash
ADBGATH_NEW_PASSWORD='PASSWORD_VALUE' adbgath web-user add analyst --password-env ADBGATH_NEW_PASSWORD
```

PowerShell example:

```powershell
$env:ADBGATH_NEW_PASSWORD = 'PASSWORD_VALUE'
adbgath web-user reset-password analyst --password-env ADBGATH_NEW_PASSWORD
Remove-Item Env:ADBGATH_NEW_PASSWORD
```

Manage a user's workspace namespace from the CLI:

```bash
adbgath web-workspace list analyst
adbgath web-workspace create analyst "Android 16 assessment"
```

The first CLI-created Web account must be an administrator.

## Security Audit / MASTG job regression

ADB-Gath 3.7 replaces the legacy Web `/api/jobs` request boundary with an explicit tenant-aware contract. `security` and `mastg` remain catalogued long-running operations and are queued in the selected user's workspace.

The frontend also normalizes FastAPI validation structures into readable messages, so a structured HTTP 422 response no longer appears as `[object Object]`.

## Logout and account disable

Signing out deletes the current session. Disabling a user revokes every existing session for that account. Password resets revoke existing sessions. The final enabled administrator cannot be disabled.

## Uninstall behavior

The 3.7 server registry contains user records and isolated Web workspaces. Installers preserve it when the keep-workspace option is selected. The default server registry can be removed along with normal workspace data during a full uninstall. A custom `ADBGATH_SERVER_HOME` should be reviewed explicitly before deletion.

## Deployment guidance

For access from another host:

- prefer the automatic TLS mode or a certificate issued by your normal CA;
- use `--insecure-http` only on a trusted isolated network or behind a trusted TLS terminator;
- use a strong startup `--remote-token` and protect it as a bootstrap secret;
- complete first-run setup from a trusted administrative client;
- create individual Web accounts instead of sharing a password;
- do not expose plaintext HTTP directly to the public Internet;
- keep `ADBGATH_SERVER_HOME` on a filesystem whose OS permissions are restricted to the ADB-Gath service account;
- back up the server registry and user workspace trees together if account/workspace continuity is required.
