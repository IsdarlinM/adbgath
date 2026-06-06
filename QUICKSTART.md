# Quick Start

## 1. Prepare ADB

Install Android SDK Platform Tools and verify ADB:

```bash
adb version
```

## 2. Connect A Device

### USB Debugging

1. Enable Developer Options on the phone.
2. Enable USB Debugging.
3. Connect the phone by USB.
4. Accept the debugging prompt.

```bash
adb devices
```

### Wireless Debugging

Pair/connect first when Android asks for it:

```bash
adb pair 192.168.1.50:37123
adb connect 192.168.1.50:5555
adb devices
```

## 3. Pick Device And Profile

```bash
chmod +x adbgath.sh
./adbgath.sh
./adbgath.sh --devices
./adbgath.sh --device emulator-5554 -l users
```

Running `./adbgath.sh` with no arguments opens interactive mode. After `make install`, the same flow is available with `adbgath`.

Device marks:

- `r`: rooted/relevant device.
- `i`: non-rooted/irrelevant device.

Install/uninstall/replace require both `--device` and `--user`.

## Common Commands

```bash
# Download all APKs
./adbgath.sh --device emulator-5554 -d

# Download all APKs to a folder
./adbgath.sh --device emulator-5554 -d -o ./apk_backup

# Download specific APK paths
./adbgath.sh --device emulator-5554 -d /data/app/com.example.app/base.apk

# Install APKs for owner profile
./adbgath.sh --device emulator-5554 --user 0 -I app.apk

# Uninstall packages for current profile
./adbgath.sh --device emulator-5554 --user current -U com.example.app

# Replace a package for profile 10
./adbgath.sh --device emulator-5554 --user 10 -R app.apk com.example.app

# List packages, APK paths, users
./adbgath.sh --device emulator-5554 -l packages
./adbgath.sh --device emulator-5554 -l paths
./adbgath.sh --device emulator-5554 -l users
```

## Logs

```bash
# Live logcat
./adbgath.sh --device emulator-5554 logs listen

# Capture app logs for 60 seconds
./adbgath.sh --device emulator-5554 logs capture --package com.example.app -o ./logs --duration 60

# Capture logs matching a regex
./adbgath.sh --device emulator-5554 logs capture --regex "token|password" -o logcat.log
```

## Rooted Network Capture

```bash
./adbgath.sh --device emulator-5554 sniff interfaces
./adbgath.sh --device emulator-5554 sniff push-tcpdump ./tcpdump
./adbgath.sh --device emulator-5554 sniff capture --interface wlan0 -o ./captures --duration 60
```

## File Inputs

Download/install/uninstall files use one item per line:

```text
/data/app/com.example.one/base.apk
/data/app/com.example.two/base.apk
```

Replacement files use one pair per line:

```text
app1.apk com.example.one
app2.apk com.example.two
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ADB is not installed` | Install Android SDK Platform Tools or set `ADB_PATH`. |
| Device not shown | Enable USB/Wireless Debugging and run `adb devices`. |
| Multiple devices | Run `./adbgath.sh --devices` and pass `--device ID`. |
| Unauthorized device | Accept the debugging prompt on the phone. |
| Install/uninstall/replace error | Pass both `--device` and `--user`. |
| Wireless device missing | Run `adb connect IP:PORT` again. |
| Permission denied | Run `chmod +x adbgath.sh`. |
