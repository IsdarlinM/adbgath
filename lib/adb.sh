#!/bin/bash

################################################################################
# ADB Library - core ADB functions with USB/Wireless and multi-device support
################################################################################

[[ -z "${UTILS_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/utils.sh"

ADB_BIN="${ADB_PATH:-adb}"
DEVICE_ID="${DEVICE_ID:-}"
USER_ID="${USER_ID:-}"

adb_command() {
    if [ -n "${DEVICE_ID:-}" ]; then
        "$ADB_BIN" -s "$DEVICE_ID" "$@"
    else
        "$ADB_BIN" "$@"
    fi
}

_adb_cmd() {
    if [ -n "${DEVICE_ID:-}" ]; then
        echo "$ADB_BIN -s $DEVICE_ID"
    else
        echo "$ADB_BIN"
    fi
}

adb_check_installed() {
    if ! command_exists "$ADB_BIN"; then
        error "ADB is not installed or not in PATH. Set ADB_PATH if you use a custom location."
    fi

    debug "ADB found: $(command -v "$ADB_BIN")"
}

adb_normalize_connect_target() {
    local target=$1

    if [[ "$target" != *:* ]]; then
        target="${target}:5555"
    fi

    echo "$target"
}

adb_connect_device() {
    local target
    target=$(adb_normalize_connect_target "$1")

    info "Connecting to wireless device: ${CYAN}$target${NC}"

    local output
    if ! output=$("$ADB_BIN" connect "$target" 2>&1); then
        error "Could not connect to $target: $output"
    fi

    echo "$output"

    if ! echo "$output" | grep -qiE "connected|already connected"; then
        error "ADB did not report a successful connection to $target"
    fi

    DEVICE_ID="$target"
    export DEVICE_ID
}

adb_list_devices() {
    "$ADB_BIN" devices 2>/dev/null | awk 'NR > 1 && $2 == "device" {print $1}'
}

adb_list_devices_detailed() {
    "$ADB_BIN" devices -l 2>/dev/null | awk 'NR > 1 && NF {print}'
}

adb_get_device_state() {
    local device=$1
    "$ADB_BIN" devices 2>/dev/null | awk -v id="$device" '$1 == id {print $2; exit}'
}

adb_select_first_device() {
    local devices=()
    mapfile -t devices < <(adb_list_devices)

    if [ "${#devices[@]}" -eq 0 ]; then
        return 1
    fi

    if [ "${#devices[@]}" -gt 1 ]; then
        return 2
    fi

    DEVICE_ID="${devices[0]}"
    export DEVICE_ID
    debug "Auto-selected device: $DEVICE_ID"
    return 0
}

adb_check_device() {
    if [ -n "${DEVICE_ID:-}" ]; then
        local state
        state=$(adb_get_device_state "$DEVICE_ID")

        case "$state" in
            device)
                debug "Selected device is online: $DEVICE_ID"
                return 0
                ;;
            unauthorized)
                error "Device '$DEVICE_ID' is unauthorized. Accept the debugging prompt on the device."
                ;;
            offline)
                error "Device '$DEVICE_ID' is offline. Reconnect USB or run 'adb connect' again."
                ;;
            "")
                error "Device '$DEVICE_ID' was not found in 'adb devices'."
                ;;
            *)
                error "Device '$DEVICE_ID' is not ready. Current state: $state"
                ;;
        esac
    fi

    if adb_select_first_device; then
        :
    else
        local selection_status=$?

        case "$selection_status" in
            1)
                error "No Android device connected. Enable USB Debugging or connect with Wireless Debugging."
                ;;
            2)
                error "Multiple Android devices are connected. Run --devices and select one with --device ID."
                ;;
            *)
                error "Could not select an Android device."
                ;;
        esac
    fi

    info "Using device: ${CYAN}$DEVICE_ID${NC} (${CYAN}$(adb_get_connection_type "$DEVICE_ID")${NC})"
}

adb_get_connection_type() {
    local device=${1:-${DEVICE_ID:-}}

    if [[ "$device" =~ :[0-9]+$ ]]; then
        echo "wireless"
    else
        echo "usb"
    fi
}

adb_get_serial() {
    if [ -n "${DEVICE_ID:-}" ]; then
        echo "$DEVICE_ID"
        return 0
    fi

    adb_list_devices | head -n 1
}

adb_get_prop() {
    local prop=$1
    adb_command shell getprop "$prop" 2>/dev/null | tr -d '\r' || echo "N/A"
}

adb_get_prop_for_device() {
    local device=$1
    local prop=$2
    "$ADB_BIN" -s "$device" shell getprop "$prop" 2>/dev/null | tr -d '\r' || echo "N/A"
}

adb_get_props() {
    local prop
    for prop in "$@"; do
        adb_get_prop "$prop"
    done
}

adb_shell() {
    adb_command shell "$@" 2>/dev/null
}

adb_shell_for_device() {
    local device=$1
    shift
    "$ADB_BIN" -s "$device" shell "$@" 2>/dev/null
}

adb_exec_out() {
    adb_command exec-out "$@" 2>/dev/null
}

adb_push() {
    local local_file=$1
    local remote_path=$2

    debug "Pushing $local_file to $remote_path"
    adb_command push "$local_file" "$remote_path" >/dev/null
}

adb_pull() {
    local remote_file=$1
    local local_path=${2:-.}

    debug "Pulling $remote_file to $local_path"
    adb_command pull "$remote_file" "$local_path" >/dev/null
}

adb_file_size() {
    local file=$1
    local size

    size=$(adb_shell stat -c%s "$file" | tr -d '\r' | head -n 1 || true)

    if [[ "$size" =~ ^[0-9]+$ ]]; then
        echo "$size"
    else
        echo "0"
    fi
}

adb_file_exists() {
    local file=$1
    adb_shell test -f "$file"
}

adb_get_packages() {
    local user_id=${1:-}

    if [ -n "$user_id" ]; then
        adb_shell pm list packages --user "$user_id" | sed 's/^package://'
    else
        adb_shell pm list packages | sed 's/^package://'
    fi
}

adb_get_users() {
    adb_shell pm list users | tr -d '\r'
}

adb_get_current_user() {
    adb_shell am get-current-user | tr -d '\r' || echo "N/A"
}

adb_get_package_path() {
    local package=$1
    local user_id=${2:-}

    if [ -n "$user_id" ]; then
        adb_shell pm path --user "$user_id" "$package" | sed 's/^package://'
    else
        adb_shell pm path "$package" | sed 's/^package://'
    fi
}

adb_get_apk_paths() {
    local user_id=${1:-}
    local packages
    packages=$(adb_get_packages "$user_id" || true)

    if [ -z "$packages" ]; then
        return 0
    fi

    while IFS= read -r package; do
        [ -z "$package" ] && continue
        adb_get_package_path "$package" "$user_id"
    done <<< "$packages"
}

adb_install_apk() {
    local apk_file=$1
    local user_id=${2:-}
    local output
    local install_args=(install)

    debug "Installing APK: $apk_file"

    if [ -n "$user_id" ]; then
        install_args+=(--user "$user_id")
    fi

    install_args+=("$apk_file")

    if output=$(adb_command "${install_args[@]}" 2>&1); then
        if echo "$output" | grep -qi "Success"; then
            return 0
        fi
    fi

    debug "Install output: $output"
    return 1
}

adb_install_apk_replace() {
    local apk_file=$1
    local user_id=${2:-}
    local output
    local install_args=(install -r)

    debug "Installing APK with -r: $apk_file"

    if [ -n "$user_id" ]; then
        install_args+=(--user "$user_id")
    fi

    install_args+=("$apk_file")

    if output=$(adb_command "${install_args[@]}" 2>&1); then
        if echo "$output" | grep -qi "Success"; then
            return 0
        fi
    fi

    debug "Install output: $output"
    return 1
}

adb_uninstall_package() {
    local package=$1
    local user_id=${2:-}
    local output
    local uninstall_args=(uninstall)

    debug "Uninstalling package: $package"

    if [ -n "$user_id" ]; then
        uninstall_args+=(--user "$user_id")
    fi

    uninstall_args+=("$package")

    if output=$(adb_command "${uninstall_args[@]}" 2>&1); then
        if echo "$output" | grep -qi "Success"; then
            return 0
        fi
    fi

    debug "Uninstall output: $output"
    return 1
}

adb_get_devices() {
    adb_list_devices
}

adb_reboot() {
    local mode=${1:-}

    if [ -n "$mode" ]; then
        debug "Rebooting device to $mode"
        adb_command reboot "$mode" >/dev/null
    else
        debug "Rebooting device"
        adb_command reboot >/dev/null
    fi
}

adb_clear_app_data() {
    local package=$1
    local user_id=${2:-}
    debug "Clearing app data for: $package"

    if [ -n "$user_id" ]; then
        adb_command shell pm clear --user "$user_id" "$package" >/dev/null
    else
        adb_command shell pm clear "$package" >/dev/null
    fi
}

export -f adb_command _adb_cmd adb_check_installed
export -f adb_normalize_connect_target adb_connect_device
export -f adb_list_devices adb_list_devices_detailed adb_get_device_state
export -f adb_select_first_device adb_check_device adb_get_connection_type
export -f adb_get_serial adb_get_prop adb_get_prop_for_device adb_get_props
export -f adb_shell adb_shell_for_device adb_exec_out adb_push adb_pull adb_file_size adb_file_exists
export -f adb_get_packages adb_get_users adb_get_current_user
export -f adb_get_package_path adb_get_apk_paths
export -f adb_install_apk adb_install_apk_replace adb_uninstall_package
export -f adb_get_devices adb_reboot adb_clear_app_data

ADB_SOURCED=true
export ADB_SOURCED
