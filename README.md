# adbgath

adbgath extracts, downloads, installs, uninstalls, and replaces APKs, collects device information, monitors logs, and captures rooted network traffic through ADB.

The script supports USB Debugging and Wireless Debugging. Running it with no arguments opens interactive mode. Read-only commands auto-select a device only when exactly one device is connected. App-changing commands require an explicit device and Android user/profile.

## Features

- Download all APKs, selected APK paths, or paths listed in a file.
- Install, uninstall, and replace apps scoped to `--device` and `--user`.
- List devices, packages, APK paths, and Android users/profiles.
- Mark rooted devices as green `r` relevant and non-rooted devices as yellow `i` irrelevant.
- Collect device metadata, packages, settings, network data, and a logcat snapshot.
- Listen to live `logcat` output or capture logs to files with package/PID/regex filters.
- Capture rooted network traffic to `.pcap` files with on-device `tcpdump`.
- Connect to wireless debugging targets with `--connect`.

## Requirements

- Bash 4.0 or newer
- ADB in `PATH`, or `ADB_PATH=/path/to/adb`
- Android device with USB Debugging or Wireless Debugging enabled
- Optional: `pv` for per-file transfer progress during downloads
- Optional/rooted: `tcpdump` on-device for network captures

## Quick Usage

```bash
chmod +x adbgath.sh

./adbgath.sh
./adbgath.sh --devices
./adbgath.sh --device emulator-5554 -l users
./adbgath.sh --device emulator-5554 -i basic
```

After `make install`, use the global command:

```bash
adbgath
adbgath --help
```

## Download APKs

```bash
./adbgath.sh --device emulator-5554 -d
./adbgath.sh --device emulator-5554 -d /data/app/com.example.app/base.apk
./adbgath.sh --device emulator-5554 -d -f examples/apk_list.txt
./adbgath.sh --device emulator-5554 -d -o ./apk_backup
```

Use `--user` to enumerate APKs installed for a specific profile:

```bash
./adbgath.sh --device emulator-5554 --user 10 -d
```

## Install APKs

```bash
./adbgath.sh --device emulator-5554 --user 0 -I app.apk
./adbgath.sh --device emulator-5554 --user current install app1.apk app2.apk
./adbgath.sh --device emulator-5554 --user 10 -I -f apk_files.txt
```

## Uninstall Packages

```bash
./adbgath.sh --device emulator-5554 --user 0 -U com.example.app
./adbgath.sh --device emulator-5554 --user current uninstall com.example.one com.example.two
./adbgath.sh --device emulator-5554 --user 10 -U -f package_list.txt
```

## Replace Apps

Replace means: uninstall the old package for the selected profile, then install the new APK for the same profile.

```bash
./adbgath.sh --device emulator-5554 --user 0 -R app.apk com.example.app
./adbgath.sh --device emulator-5554 --user current replace com.example.app app.apk
./adbgath.sh --device emulator-5554 --user 10 -R -f replacements.txt
```

Replacement file format:

```text
app1.apk com.example.one
app2.apk com.example.two
```

## Logs

Log monitoring follows OWASP MASTG-TECH-0009 guidance for Android `logcat`.

```bash
./adbgath.sh --device emulator-5554 logs listen
./adbgath.sh --device emulator-5554 logs listen --package com.example.app
./adbgath.sh --device emulator-5554 logs capture --package com.example.app -o ./logs --duration 60
./adbgath.sh --device emulator-5554 logs capture --pid 1234 --regex "token|password" -o logcat.log
./adbgath.sh --device emulator-5554 logs clear
```

Useful log options:

- `--package <NAME>` resolves the running app PID and filters logcat by it.
- `--pid <PID>` filters directly by PID.
- `--regex <EXPR>` applies logcat regex filtering.
- `--filter <SPEC>` adds tag/priority filters such as `ActivityManager:I`.
- `--clear-logs` clears the logcat buffer before listening/capturing.
- `--duration <SECONDS>` stops automatically.

## Network Capture

Network capture follows OWASP MASTG-TECH-0010 concepts and requires a rooted device or accessible `su`, plus `tcpdump`.

```bash
./adbgath.sh --device emulator-5554 sniff interfaces
./adbgath.sh --device emulator-5554 sniff push-tcpdump ./tcpdump
./adbgath.sh --device emulator-5554 sniff capture --interface wlan0 -o ./captures --duration 60
```

## Wireless Debugging

For Android 11+, pair/connect with ADB when required:

```bash
adb pair 192.168.1.50:37123
adb connect 192.168.1.50:5555
adb devices
```

Then use the ID shown by `adb devices`:

```bash
./adbgath.sh --device 192.168.1.50:5555 -i network
```

You can also ask the script to connect:

```bash
./adbgath.sh --connect 192.168.1.50:5555 -d
```

## Configuration

```bash
export OUTPUT_DIR="/path/to/downloads"
export DEVICE_ID="emulator-5554"
export USER_ID="0"
export VERBOSE=true
export ADB_PATH="/custom/path/to/adb"
```

## More Commands

```bash
./adbgath.sh --devices
./adbgath.sh --device emulator-5554 -l packages
./adbgath.sh --device emulator-5554 -l paths
./adbgath.sh --device emulator-5554 -l users
./adbgath.sh --device emulator-5554 -i security
./adbgath.sh --device emulator-5554 -C -o ./device_collection
./adbgath.sh --help
./adbgath.sh --version
```

## Troubleshooting

- `ADB is not installed`: install Android SDK Platform Tools or set `ADB_PATH`.
- `Multiple Android devices are connected`: run `--devices` and pass `--device ID`.
- `Device is unauthorized`: unlock the phone and accept the RSA/debugging prompt.
- Install/uninstall/replace fails: verify `--device`, `--user`, and package/APK arguments.
- `Package is not running` in logs: start the app or pass `--pid`.
- `tcpdump was not found`: use `sniff push-tcpdump ./tcpdump` on rooted test devices.
