#!/bin/bash

################################################################################
# Discovery and connection helpers for authorized ADB auditing.
################################################################################

[[ -z "${ADB_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/adb.sh"
[[ -z "${CONFIG_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

adb_discover_devices() {
    local devices_output
    devices_output=$(adb devices 2>/dev/null || true)
    echo "$devices_output"
}

adb_validate_device_state() {
    local device_id=${1:-}
    if [ -z "$device_id" ]; then
        echo "invalid"
        return 0
    fi

    local state
    state=$(adb -s "$device_id" get-state 2>/dev/null || true)
    case "$state" in
        device) echo "ready" ;;
        unauthorized) echo "unauthorized" ;;
        offline) echo "offline" ;;
        "") echo "unknown" ;;
        *) echo "$state" ;;
    esac
}

adb_connect_with_retry() {
    local target=$1
    local timeout=${2:-${ADDBGATH_TIMEOUT:-10}}
    local retries=${3:-2}
    local attempt=1
    local output

    while [ "$attempt" -le "$retries" ]; do
        if output=$(adb connect "$target" 2>&1); then
            echo "$output"
            return 0
        fi
        if [ "$attempt" -ge "$retries" ]; then
            echo "$output" >&2
            return 1
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
}

export -f adb_discover_devices adb_validate_device_state adb_connect_with_retry

DISCOVERY_SOURCED=true
export DISCOVERY_SOURCED
