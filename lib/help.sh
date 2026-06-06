#!/bin/bash

################################################################################
# Help Library - CLI usage text and terminal branding
################################################################################

show_logo() {
    printf "%b" "${CYAN}"
    cat << 'EOF'
      _       ____  ____   ____    _  _____ _   _
     / \     |  _ \| __ ) / ___|  / \|_   _| | | |
    / _ \    | | | |  _ \| |  _  / _ \ | | | |_| |
   / ___ \   | |_| | |_) | |_| |/ ___ \| | |  _  |
  /_/   \_\  |____/|____/ \____/_/   \_\_| |_| |_|
EOF
    printf "%b\n" "${NC}"
    printf "%b\n" "${BLUE}                 Android Debug Bridge Gatherer${NC}"
}

cli_display_name() {
    local cli="${SCRIPT_NAME:-adbgath}"

    if [[ "$cli" == *.sh ]]; then
        cli="./$cli"
    fi

    echo "$cli"
}

show_help() {
    local cli
    cli="$(cli_display_name)"

    show_logo
    echo

    cat << EOF
adbgath v$VERSION

USAGE:
  $cli [GLOBAL OPTIONS] [COMMAND] [COMMAND OPTIONS] [ARGS]
  $cli [GLOBAL OPTIONS] -d [APK_PATH...]
  $cli

GLOBAL OPTIONS:
  -D, --device, -s <ID>       Use a specific device from "adb devices"
      --connect <IP[:PORT]>   Connect to a wireless device, then use it
      --devices               List connected devices with root relevance marks
  -u, --user, --profile <ID>  Android user/profile for scoped operations
                              Accepts numeric IDs, "current", "owner", "primary"
  -o, --output <PATH>         Output directory or file, depending on command
  -f, --file <FILE>           Read command input from file
      --verbose               Show debug output
  -h, --help                  Show this help
  -v, --version               Show version

COMMANDS:
  download, -d, --download    Download APKs
  install,  -I, --install     Install one or more APK files
  uninstall,-U, --uninstall   Uninstall one or more package names
  replace,  -R, --replace     Uninstall a package and install an APK
  list,     -l, --list        List packages, APK paths, users, or devices
  info,     -i, --info        Show device information
  collect,  -C, --collect     Collect device information through ADB
  logs, logcat               Listen to or capture Android logcat output
  sniff, pcap                Capture network traffic with tcpdump on rooted devices

TARGETING DEVICES AND USERS:
  Read-only commands auto-select only when exactly one device is connected.
  Install/uninstall/replace always require an explicit device and user/profile:
    $cli --devices
    $cli --device emulator-5554 -l users
    $cli --device emulator-5554 --user 0 -I app.apk

DEVICE LIST MARKS:
  r = relevant/rooted device shown in green
  i = irrelevant/non-rooted device shown in yellow

DOWNLOAD:
  $cli -d
  $cli --device emulator-5554 -d
  $cli --device emulator-5554 -d /data/app/app1/base.apk
  $cli --device emulator-5554 -d -f examples/apk_list.txt
  $cli --connect 192.168.1.50:5555 -d -o ./apk_backup

INSTALL:
  $cli --device emulator-5554 --user 0 -I app.apk
  $cli --device emulator-5554 --user current install app1.apk app2.apk
  $cli --device emulator-5554 --user 10 -I -f apk_files.txt

UNINSTALL:
  $cli --device emulator-5554 --user 0 -U com.example.app
  $cli --device emulator-5554 --user current uninstall com.one com.two
  $cli --device emulator-5554 --user 10 -U -f package_list.txt

REPLACE:
  $cli --device emulator-5554 --user 0 -R app.apk com.example.app
  $cli --device emulator-5554 --user current replace com.example.app app.apk
  $cli --device emulator-5554 --user 10 -R -f replacements.txt

LIST AND INFO:
  $cli --devices
  $cli --device emulator-5554 -l packages
  $cli --device emulator-5554 --user 10 -l packages
  $cli --device emulator-5554 -l paths
  $cli --device emulator-5554 -l users
  $cli --device emulator-5554 -i
  $cli --device emulator-5554 -i network
  $cli --device emulator-5554 -i security

COLLECT:
  $cli --device emulator-5554 -C -o ./device_collection

LOGS / LOGCAT:
  $cli --device emulator-5554 logs listen
  $cli --device emulator-5554 logs listen --package com.example.app
  $cli --device emulator-5554 logs capture --package com.example.app -o ./logs --duration 60
  $cli --device emulator-5554 logs capture --pid 1234 --regex "token|password" -o logcat.log
  $cli --device emulator-5554 logs clear

  Log options:
      --package <NAME>        Resolve the running app PID and filter logcat by it
      --pid <PID>             Filter logcat by PID directly
      --regex, --grep <EXPR>  Apply logcat regex filtering
      --filter <SPEC>         Add logcat tag/priority filter, e.g. ActivityManager:I
      --format <FORMAT>       logcat format (default: threadtime)
      --clear-logs            Clear logcat before listen/capture
      --duration <SECONDS>    Stop listen/capture automatically

NETWORK SNIFFING:
  $cli --device emulator-5554 sniff interfaces
  $cli --device emulator-5554 sniff push-tcpdump ./tcpdump
  $cli --device emulator-5554 sniff capture --interface wlan0 -o ./captures --duration 60

  Network capture requires root or an accessible su binary, plus tcpdump on-device.

WIRELESS DEBUGGING:
  Android must already be authorized for wireless debugging. If needed, run:
    adb pair IP:PAIR_PORT
    adb connect IP:DEBUG_PORT

  After that, use the device ID shown by "adb devices", for example:
    $cli --device 192.168.1.50:5555 -i network

FILE FORMATS:
  Download/install/uninstall files: one item per line.
  Replace files: APK_FILE PACKAGE_NAME, one pair per line.
  Blank lines and lines starting with # are ignored.

MASTG REFERENCES:
  MASTG-TECH-0009: Monitoring System Logs with logcat
  MASTG-TECH-0010: Basic Network Monitoring/Sniffing with tcpdump
EOF
}

export -f show_logo cli_display_name show_help

HELP_SOURCED=true
export HELP_SOURCED
