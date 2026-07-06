#!/bin/bash

################################################################################
# Application inventory and permission helpers.
################################################################################

[[ -z "${ADB_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/adb.sh"
[[ -z "${CONFIG_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

apps_list_packages() {
    local device_id=${1:-${DEVICE_ID:-}}
    adb -s "$device_id" shell pm list packages 2>/dev/null | sed 's/^package://'
}

apps_list_permissions() {
    local device_id=${1:-${DEVICE_ID:-}}
    local pkg=${2:-}
    if [ -n "$pkg" ]; then
        adb -s "$device_id" shell dumpsys package "$pkg" 2>/dev/null | grep -E 'permission|granted=' || true
    else
        adb -s "$device_id" shell dumpsys package 2>/dev/null | grep -E 'permission|granted=' | head -n 50 || true
    fi
}

export -f apps_list_packages apps_list_permissions

APPS_PERMISSIONS_SOURCED=true
export APPS_PERMISSIONS_SOURCED
