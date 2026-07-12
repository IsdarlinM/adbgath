# Quick start

## Windows

```bat
installers\windows\install.cmd
```

Open a new terminal:

```bat
adbgath doctor
adb devices -l
adbgath devices
adbgath web
```

## Linux

```bash
chmod +x installers/linux/install.sh
./installers/linux/install.sh
adbgath doctor
adb devices -l
adbgath devices
adbgath web
```

## Select a target

```bash
adbgath --device SERIAL list users
adbgath --device SERIAL --user current list packages --include-paths
```

State-changing operations require both an explicit device and profile:

```bash
adbgath --device SERIAL --user 0 install ./app.apk
adbgath --device SERIAL --user 0 uninstall com.example.app
```

## Batch input

One package or APK path per line:

```bash
adbgath --device SERIAL --user current download --file examples/packages.txt
adbgath --device SERIAL --user 0 uninstall --file examples/packages.txt
adbgath --device SERIAL --user 0 install --file examples/apks.txt
```

Replacement file format:

```text
"C:/path with spaces/replacement.apk" com.example.app
```

```bash
adbgath --device SERIAL --user 0 replace --file examples/replacements.txt
```

## Local web workspace

```bash
adbgath web
```

Open `http://127.0.0.1:8765`. Select the device and profile before running operations. Destructive operations require the authorization checkbox.
