# Examples

This directory contains sample inputs and command examples for ADB APK Gatherer.

## Files

- `apk_list.txt`: one device APK path per line, used by `-d -f`.
- `usage_examples.sh`: printable examples for download, install, uninstall, replace, logs, sniffing, USB, and wireless debugging.

## Common Workflows

### List Devices

```bash
../adbgath.sh --devices
```

Use the ID printed by `adb devices`:

```bash
../adbgath.sh --device emulator-5554 -i basic
../adbgath.sh --device 192.168.1.50:5555 -l packages
```

Device marks:

- `r`: rooted/relevant device.
- `i`: non-rooted/irrelevant device.

### List Users/Profiles

```bash
../adbgath.sh --device emulator-5554 -l users
```

### Wireless Debugging

Pair/connect with ADB first if Android requires it:

```bash
adb pair 192.168.1.50:37123
adb connect 192.168.1.50:5555
../adbgath.sh --device 192.168.1.50:5555 -i network
```

Or connect from the script:

```bash
../adbgath.sh --connect 192.168.1.50:5555 -d
```

### Backup APKs

```bash
mkdir -p ~/android_apk_backup
../adbgath.sh --device emulator-5554 -d -o ~/android_apk_backup
```

### Download Specific Apps

```bash
../adbgath.sh --device emulator-5554 -d \
  /data/app/com.example.app1/base.apk \
  /data/app/com.example.app2/base.apk
```

### Download From A File

```bash
../adbgath.sh --device emulator-5554 -d -f apk_list.txt
```

### Install, Uninstall, Replace

```bash
../adbgath.sh --device emulator-5554 --user 0 -I app.apk
../adbgath.sh --device emulator-5554 --user current -U com.example.app
../adbgath.sh --device emulator-5554 --user 10 -R app.apk com.example.app
```

For replacements from a file:

```text
app1.apk com.example.one
app2.apk com.example.two
```

Then run:

```bash
../adbgath.sh --device emulator-5554 --user 0 -R -f replacements.txt
```

### Logs

```bash
../adbgath.sh --device emulator-5554 logs listen --package com.example.app
../adbgath.sh --device emulator-5554 logs capture --package com.example.app -o ./logs --duration 60
```

### Rooted Network Capture

```bash
../adbgath.sh --device emulator-5554 sniff interfaces
../adbgath.sh --device emulator-5554 sniff push-tcpdump ./tcpdump
../adbgath.sh --device emulator-5554 sniff capture --interface wlan0 -o ./captures --duration 60
```
