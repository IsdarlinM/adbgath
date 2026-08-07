# Wireless Debugging

ADB-Gath 3.3.0 supports Android 11+ Wireless Debugging through the **pairing code** workflow. QR pairing is not implemented in this release.

## Pairing and connecting use different ports

Android publishes two mDNS service types:

- `_adb-tls-pairing._tcp`: temporary service used only by `adb pair`.
- `_adb-tls-connect._tcp`: service used by `adb connect` after pairing.

The pairing port can disappear when pairing succeeds, the dialog expires, or the Android pairing dialog closes. Calling `connect` against that temporary port can therefore return `failed to connect` or Windows socket error `10061`.

## CLI workflow

On Android:

1. Open **Developer options**.
2. Open **Wireless debugging**.
3. Enable Wireless debugging for the current trusted network.
4. Select **Pair device with pairing code**.
5. Keep the dialog open while pairing.

On the workstation:

```bash
adbgath wireless discover
adbgath wireless pair 172.18.9.245:42029
```

Enter the six-digit code when prompted. The code:

- is passed only through standard input;
- is not part of the process arguments;
- is not saved in command history, SQLite, jobs, reports, presets, metrics, or artifacts;
- is cleared from the Web UI after every attempt.

After successful pairing, use the IP and port shown on the main Android **Wireless debugging** screen:

```bash
adbgath wireless connect 172.18.9.245:40587
adbgath devices --details
```

The pairing and connection ports normally differ.

A short alias is also available:

```bash
adbgath pair 172.18.9.245:42029
```

## Discovery and monitoring

```bash
adbgath wireless discover
adbgath wireless watch --interval 3
```

ADB-Gath first attempts:

```text
adb mdns track-services --proto-text
```

and falls back to:

```text
adb mdns services
```

Parsed fields can include service type, instance, IPv4, bracketed IPv6, `.local` hostname, port, model, given name, serial, Android SDK metadata and mDNS service version.

## Diagnostics

```bash
adbgath wireless status
adbgath wireless diagnose
```

Diagnostics inspect Platform-Tools, `adb server-status`, `mdns_enabled`, the mDNS backend, advertised pairing/connection services, current transports and locally known targets.

Safe repair for the current process:

```bash
adbgath wireless diagnose --fix
```

ADB-Gath-scoped persistent repair:

```bash
adbgath wireless diagnose --fix --persist
```

The persistent option writes only these non-secret values to `ADBGATH_HOME/wireless.env`:

```text
ADB_MDNS=1
ADB_MDNS_OPENSCREEN=0
```

It does not modify Android settings or globally edit operating-system environment variables.

## Semantic success detection

Some ADB networking builds return process exit code `0` while printing a failure such as:

```text
failed to connect to HOST:PORT
cannot connect to HOST:PORT: ... actively refused it. (10061)
```

ADB-Gath evaluates both the return code and ADB output and returns `ok: false` with `semantic_failure: adb-textual-failure` for these cases.

## Known targets

```bash
adbgath wireless known
adbgath wireless alias TARGET_ID "SOC Android Lab"
adbgath wireless forget TARGET_ID
```

ADB-Gath stores only non-secret discovery and connection metadata. `forget` removes the local ADB-Gath record; revoke workstation trust from Android's Wireless debugging settings.

## Auto-connect

```bash
adbgath wireless auto-connect
```

This attempts connection only to currently discovered `_adb-tls-connect._tcp` services. It does not scan IP ranges, guess ports, brute-force codes or bypass Android trust prompts.

## Legacy USB-assisted TCP/IP mode

For an explicitly selected USB-authorized device:

```bash
adbgath --device USB_SERIAL wireless tcpip --port 5555
adbgath wireless connect 192.168.1.50:5555
```

This is separate from Android 11+ TLS pairing.

## Web UI

Start the local console and open `/wireless`:

```bash
adbgath web
```

The Wireless workspace provides discovery, live mDNS updates, password-style code entry, pairing, connect/disconnect, auto-connect, diagnostics, ADB-Gath-scoped repair, aliases and local target removal. Pairing cannot be queued as a persistent background job.

## Troubleshooting

### Windows error 10061

- Keep the Android pairing dialog open while pairing.
- Use `pair`, not `connect`, with the temporary pairing endpoint.
- Use the connection port from Android's main Wireless debugging screen after pairing.
- Verify both systems are on the same trusted network.
- Check AP/client isolation, guest Wi-Fi, VPN and firewall behavior.

### No mDNS services

```bash
adbgath wireless diagnose
adbgath wireless diagnose --fix --persist
```

If discovery remains empty, manually enter the endpoints displayed by Android.

### Paired but not connected

```bash
adbgath wireless discover
adbgath wireless auto-connect
adbgath devices --watch
```

Android can rotate the connection port after network or service changes.
