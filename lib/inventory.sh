#!/bin/bash

################################################################################
# Basic inventory helpers for authorized Android device assessment.
################################################################################

[[ -z "${ADB_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/adb.sh"
[[ -z "${CONFIG_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

inventory_basic() {
    local device_id=${1:-${DEVICE_ID:-}}
    local output_dir=${2:-$(config_get_output_dir)}
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local report_file="$output_dir/inventory_${timestamp}.json"

    mkdir -p "$output_dir"

    local payload
    payload=$(cat <<EOF
{
  "device_id": "${device_id}",
  "timestamp": "${timestamp}",
  "model": "$(adb -s "$device_id" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || echo 'N/A')",
  "manufacturer": "$(adb -s "$device_id" shell getprop ro.product.manufacturer 2>/dev/null | tr -d '\r' || echo 'N/A')",
  "android_version": "$(adb -s "$device_id" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r' || echo 'N/A')",
  "api_level": "$(adb -s "$device_id" shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\r' || echo 'N/A')",
  "build_id": "$(adb -s "$device_id" shell getprop ro.build.display.id 2>/dev/null | tr -d '\r' || echo 'N/A')",
  "security_patch": "$(adb -s "$device_id" shell getprop ro.build.version.security_patch 2>/dev/null | tr -d '\r' || echo 'N/A')"
}
EOF
)

    printf '%s\n' "$payload" > "$report_file"
    echo "$report_file"
}

export -f inventory_basic

INVENTORY_SOURCED=true
export INVENTORY_SOURCED
