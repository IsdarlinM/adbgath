# Quick start

## 1. Install

### Windows

```bat
installers\windows\install.cmd
```

### Linux

```bash
chmod +x installers/linux/install.sh
./installers/linux/install.sh
```

## 2. Validate the host

```bash
adbgath --version
adbgath doctor --fix
adb devices -l
adbgath devices
```

Approve the ADB RSA prompt on the device before continuing.

## 3. Inspect profiles and packages

```bash
adbgath --device SERIAL list users
adbgath --device SERIAL --user current list packages --include-paths
adbgath --device SERIAL app com.example.app
```

## 4. Create a project

```bash
adbgath project create "Authorized Android assessment" --scope com.example.app
adbgath project list
```

Copy the generated project ID.

## 5. Run an assessment

```bash
adbgath --device SERIAL assess com.example.app --project-id PROJECT_ID
```

## 6. Capture evidence

```bash
adbgath --device SERIAL evidence \
  --package com.example.app \
  --screen-record 10 \
  --output ./evidence
```

## 7. Export reports

```bash
adbgath report PROJECT_ID --format html
adbgath report PROJECT_ID --format pdf
adbgath report PROJECT_ID --format sarif
adbgath project export PROJECT_ID --output ./project-evidence.zip
```

## 8. Open the web workspace

```bash
adbgath web
```

Open `http://127.0.0.1:8765`.

## Common APK commands

```bash
adbgath --device SERIAL --user current download com.example.app
adbgath --device SERIAL --user 0 install app.apk --replace
adbgath --device SERIAL --user 0 install-set ./split-apks
adbgath --device SERIAL --user 0 replace com.example.app replacement.apk
```

Add `--allow-uninstall` to `replace` only after reviewing signature compatibility and data-loss implications.

## Optional controlled Frida observation

```bash
adbgath frida scripts
adbgath --device SERIAL frida attach --package com.example.app --script tls-observer
adbgath frida history --limit 25
```

Stored session logs are redacted by default.
