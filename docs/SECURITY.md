# Security design and threat model

## Intended use

adbgath is designed for authorized Android assessment, defensive evidence collection, development labs, emulators, CTFs, and in-scope bug-bounty testing.

## Host-side command safety

`AdbClient` invokes `adb` with `subprocess.run()` or `subprocess.Popen()` using argument arrays and `shell=False`. Inputs do not pass through `cmd.exe`, PowerShell, Bash, or another command interpreter.

Validated inputs include:

- ADB serials.
- Android package names.
- Android profile identifiers.
- Wireless host/port values.
- Remote Android paths.
- Network interface names.
- Durations and port numbers.
- Local artifact and upload paths.

The packet-capture command uses `su -c` on the Android device because root execution is required. The interpolated values are restricted to validated numeric durations, known tcpdump paths, generated capture paths, and validated interface names.

## Web threat model

The web interface assumes an interactive user on the same host. It is not intended for public or shared-network exposure.

Controls:

- Loopback-only binding with no remote override.
- Random per-process session cookie.
- Trusted host allowlist.
- Same-origin frontend.
- No CORS relaxation.
- No arbitrary shell endpoint.
- Backend action allowlist.
- Explicit confirmation for destructive actions.
- Workspace confinement for downloads.
- Security headers.

## Sensitive artifacts

Collections may contain package inventories, logs, runtime details, device properties, APKs, PCAP files, or application data. Store the workspace on encrypted media, apply least-privilege filesystem permissions, and remove artifacts when the engagement retention period ends.

## Limitations

- ADB itself grants broad control once a device accepts the host key.
- Rooted packet capture and instrumentation can alter device behavior.
- `run-as` backup only works for debuggable packages or compatible device configurations.
- Android versions and OEM builds expose different command output.
- The posture audit is a baseline, not a complete security certification.
- Static APK analysis is deeper when Android build-tools are installed.
