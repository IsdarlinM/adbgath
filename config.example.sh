#!/bin/bash

################################################################################
# Configuration for ADB APK Gatherer
# Source this file to set up environment variables
#
# Usage:
#   source config.sh
#   ./adbgath.sh --verbose -d
################################################################################

# Enable verbose output (true or false)
export VERBOSE=false

# Output directory for downloaded APKs
# Default: current directory
export OUTPUT_DIR="."

# Optional device ID from "adb devices"
# Works for USB IDs, emulators, and wireless targets like 192.168.1.50:5555
# export DEVICE_ID="emulator-5554"

# Optional Android user/profile ID.
# Required for install/uninstall/replace; list profiles with:
#   ./adbgath.sh --device emulator-5554 -l users
# export USER_ID="0"

# Custom ADB command if needed
# Usually not necessary, but useful if ADB is in non-standard location
# export ADB_PATH="/custom/path/to/adb"

# Example configurations:

# Development mode - verbose logging
# export VERBOSE=true

# Download to specific directory
# export OUTPUT_DIR="/home/user/android_backups"

# For WSL (Windows Subsystem for Linux)
# export ADB_PATH="/mnt/c/Android/platform-tools/adb"

echo "Configuration loaded:"
echo "VERBOSE=$VERBOSE"
echo "OUTPUT_DIR=$OUTPUT_DIR"
[ -n "${DEVICE_ID:-}" ] && echo "DEVICE_ID=$DEVICE_ID"
[ -n "${USER_ID:-}" ] && echo "USER_ID=$USER_ID"
echo ""
echo "Run: ./adbgath.sh -h for help"
