#!/bin/bash

################################################################################
# Example usage of ADB APK Gatherer
################################################################################

SCRIPT="./adbgath.sh"

echo "ADB APK Gatherer - Usage Examples"
echo "=================================="
echo ""

if [ ! -f "$SCRIPT" ]; then
    echo "Error: adbgath.sh not found in current directory"
    exit 1
fi

chmod +x "$SCRIPT"

echo "1. List connected devices with root relevance marks"
echo "   $SCRIPT --devices"
echo "   # r = rooted/relevant, i = non-rooted/irrelevant"
echo ""

echo "2. Select a device by the ID shown in adb devices"
echo "   $SCRIPT --device emulator-5554 -i basic"
echo "   $SCRIPT --device 192.168.1.50:5555 -l packages"
echo ""

echo "3. List Android users/profiles"
echo "   $SCRIPT --device emulator-5554 -l users"
echo ""

echo "4. Connect and use a wireless debugging device"
echo "   adb pair 192.168.1.50:37123"
echo "   $SCRIPT --connect 192.168.1.50:5555 -i network"
echo ""

echo "5. Download APKs"
echo "   $SCRIPT --device emulator-5554 -d"
echo "   $SCRIPT --device emulator-5554 -d /data/app/com.example.app/base.apk"
echo "   $SCRIPT --device emulator-5554 -d /data/app/app1/base.apk /data/app/app2/base.apk"
echo "   $SCRIPT --device emulator-5554 -d -f examples/apk_list.txt"
echo "   $SCRIPT --device emulator-5554 -d -o ./apk_backup"
echo ""

echo "6. Install APKs for a specific profile"
echo "   $SCRIPT --device emulator-5554 --user 0 -I app.apk"
echo "   $SCRIPT --device emulator-5554 --user current install app1.apk app2.apk"
echo "   $SCRIPT --device emulator-5554 --user 10 -I -f apk_files.txt"
echo ""

echo "7. Uninstall packages for a specific profile"
echo "   $SCRIPT --device emulator-5554 --user 0 -U com.example.app"
echo "   $SCRIPT --device emulator-5554 --user current uninstall com.example.one com.example.two"
echo "   $SCRIPT --device emulator-5554 --user 10 -U -f package_list.txt"
echo ""

echo "8. Replace packages for a specific profile"
echo "   $SCRIPT --device emulator-5554 --user 0 -R app.apk com.example.app"
echo "   $SCRIPT --device emulator-5554 --user current replace com.example.app app.apk"
echo "   $SCRIPT --device emulator-5554 --user 10 -R app1.apk com.one app2.apk com.two"
echo "   $SCRIPT --device emulator-5554 --user 0 -R -f replacements.txt"
echo ""

echo "9. Logs and logcat capture"
echo "   $SCRIPT --device emulator-5554 logs listen"
echo "   $SCRIPT --device emulator-5554 logs listen --package com.example.app"
echo "   $SCRIPT --device emulator-5554 logs capture --package com.example.app -o ./logs --duration 60"
echo "   $SCRIPT --device emulator-5554 logs capture --pid 1234 --regex \"token|password\" -o logcat.log"
echo "   $SCRIPT --device emulator-5554 logs clear"
echo ""

echo "10. Rooted network capture"
echo "    $SCRIPT --device emulator-5554 sniff interfaces"
echo "    $SCRIPT --device emulator-5554 sniff push-tcpdump ./tcpdump"
echo "    $SCRIPT --device emulator-5554 sniff capture --interface wlan0 -o ./captures --duration 60"
echo ""

echo "11. Device information and collection"
echo "    $SCRIPT --device emulator-5554 -i"
echo "    $SCRIPT --device emulator-5554 -i security"
echo "    $SCRIPT --device emulator-5554 -C -o ./device_collection"
echo ""

echo "12. Help, version, and verbose mode"
echo "    $SCRIPT -h"
echo "    $SCRIPT -v"
echo "    $SCRIPT --verbose --device emulator-5554 -d"
echo ""

echo "==== ACTUAL COMMAND EXAMPLES ===="
echo ""
echo "Uncomment one command below to run it:"
echo ""

# $SCRIPT --devices
# $SCRIPT --device emulator-5554 -l users
# $SCRIPT --device emulator-5554 -l packages
# $SCRIPT --device emulator-5554 -l paths
# $SCRIPT --device emulator-5554 -i basic
# $SCRIPT --device emulator-5554 -d -o ./apk_backup
# $SCRIPT --device emulator-5554 --user 0 -I app.apk
# $SCRIPT --device emulator-5554 --user 0 -U com.example.app
# $SCRIPT --device emulator-5554 --user 0 -R app.apk com.example.app
# $SCRIPT --device emulator-5554 logs capture --package com.example.app -o ./logs --duration 60

echo "To run actual commands, uncomment them in this script and execute:"
echo "bash examples/usage_examples.sh"
