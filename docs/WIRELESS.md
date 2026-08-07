# Wireless Debugging

ADB-Gath 3.4.0 supports both Android 11+ Wireless Debugging workflows exposed by Android: **Pair device with QR code** and **Pair device with pairing code**.

## Trust and scope

Use these workflows only with devices you own or are explicitly authorized to assess. Wireless pairing establishes workstation trust on Android. ADB-Gath does not scan arbitrary networks, brute-force ports, bypass Android confirmation, or extract pairing credentials.

## QR pairing

On Android:

1. Open **Developer options**.
2. Open **Wireless debugging**.
3. Enable Wireless debugging on the trusted local network.
4. Select **Pair device with QR code**.

On the workstation:

```bash
adbgath wireless qr
```

ADB-Gath generates the AOSP ADB Wi-Fi QR grammar:

```text
WIFI:T:ADB;S:studio-<random-instance>;P:<one-time-secret>;;
```

The QR is compatible with the Android Wireless Debugging scanner. After the device scans it, Android advertises a temporary `_adb-tls-pairing._tcp` service whose instance matches the QR. ADB-Gath:

1. waits for that exact instance through the shared mDNS broker;
2. sends the one-time secret to `adb pair` through standard input;
3. never includes the secret in process arguments or returned metadata;
4. discovers the separate `_adb-tls-connect._tcp` service;
5. connects automatically unless disabled;
6. deletes the temporary SVG unless `--keep` is supplied.

Options:

```bash
adbgath wireless qr --timeout 180
adbgath wireless qr --no-auto-connect
adbgath wireless qr --output ./pairing.svg --open
adbgath wireless qr --keep
```

Security properties:

- random service instance and secret for every session;
- 30–300 second lifetime;
- secret held only in process memory;
- no SQLite, metrics, jobs, reports, presets, logs, shell history, or browser storage;
- Web SVG responses use `Cache-Control: no-store`;
- Web creation requires the literal authorized-target confirmation;
- terminal sessions remove the QR from the browser view.

## Pairing with a six-digit code

Android uses two different endpoints:

- `_adb-tls-pairing._tcp`: temporary endpoint used only by `adb pair`;
- `_adb-tls-connect._tcp`: endpoint used by `adb connect` after pairing.

On Android, choose **Pair device with pairing code** and keep the dialog open. Then:

```bash
adbgath wireless discover
adbgath wireless pair 172.18.9.245:42029
```

Enter the six-digit code through the protected prompt. After pairing, use the separate connection endpoint shown on the main Wireless debugging screen:

```bash
adbgath wireless connect 172.18.9.245:40587
adbgath devices --details
```

The pairing and connection ports usually differ. Reusing the temporary pairing port for `connect` commonly produces `failed to connect` or Windows socket error `10061`.

## Shared event broker

```bash
adbgath wireless broker status
adbgath wireless broker start
adbgath wireless broker stop
```

The broker centralizes ADB device and mDNS reconciliation in one bounded daemon thread. It emits ordered events for:

- pairing/connection service added, removed, or changed;
- ADB device added, removed, or changed;
- broker start, stop, snapshots, and errors.

The Web UI subscribes to this shared stream instead of spawning a discovery subprocess for every browser connection. The broker uses bounded event history and adaptive backoff after failures.

## Discovery

```bash
adbgath wireless discover
```

ADB-Gath prefers:

```text
adb mdns track-services --proto-text
```

and falls back to:

```text
adb mdns services
```

It parses IPv4, bracketed IPv6, `.local` hostnames, ports, service type, model, given name, serial, SDK metadata, and ADB Wi-Fi service version when available.

Live CLI monitoring:

```bash
adbgath wireless watch --interval 3
```

## Diagnostics and repair

```bash
adbgath wireless status
adbgath wireless diagnose
adbgath wireless diagnose --fix
adbgath wireless diagnose --fix --persist
```

Diagnostics inspect Platform-Tools, `adb server-status`, `mdns_enabled`, mDNS backend, service discovery, transports, and known targets.

Persistent repair writes only non-secret ADB-Gath-scoped values to `ADBGATH_HOME/wireless.env`:

```text
ADB_MDNS=1
ADB_MDNS_OPENSCREEN=0
```

It does not change Android settings or globally rewrite the operating-system environment.

## Semantic ADB success

Some ADB networking builds return process code `0` while printing a failure. ADB-Gath evaluates both exit status and output. Text such as `failed to connect`, `cannot connect`, authentication failure, or an actively refused socket is returned with `ok: false` and a semantic failure marker.

## Known targets

```bash
adbgath wireless known
adbgath wireless alias TARGET_ID "SOC Android Lab"
adbgath wireless forget TARGET_ID
```

Only non-secret discovery and connection metadata is stored. Removing the local record does not revoke Android trust; use Android's **Forget** action to revoke the workstation key.

## Troubleshooting

### QR remains waiting for scan

- Confirm the Android QR scanner was opened from Wireless debugging, not a generic camera app.
- Keep both devices on a network that allows multicast/mDNS.
- Run `adbgath wireless diagnose`.
- Check guest-network/AP isolation, VPN routes, and host firewall multicast rules.

### Paired but not connected

- Android may take a moment to publish `_adb-tls-connect._tcp`.
- Run `adbgath wireless discover` and `adbgath wireless auto-connect`.
- Keep Wireless debugging enabled.
- Android can rotate the connection port after network changes.

### Code pairing returns Windows error 10061

- The pairing dialog probably expired or closed.
- The endpoint may be the temporary pairing port being incorrectly reused for connection.
- Reopen the dialog, use `wireless pair`, then connect to the separate port.

## Official references

- Android Developers, Android Debug Bridge and Wireless debugging: https://developer.android.com/tools/adb
- AOSP ADB Wi-Fi design and QR payload: https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/dev/adb_wifi.md
