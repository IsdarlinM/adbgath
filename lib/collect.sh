#!/bin/bash

################################################################################
# Collection Library - gather selected Android device information through ADB
################################################################################

[[ -z "${DEVICE_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/device.sh"

collect_safe_name() {
    local value=${1:-device}
    echo "$value" | sed 's/[^A-Za-z0-9._-]/_/g'
}

collect_timestamp() {
    date "+%Y%m%d_%H%M%S"
}

collect_metadata() {
    echo "ADB APK Gatherer Device Collection"
    echo "Collected At: $(date "+%Y-%m-%d %H:%M:%S %z")"
    echo "Selected Device: $(adb_get_serial)"
    echo "Connection Type: $(adb_get_connection_type)"
    echo "Model: $(device_get_model)"
    echo "Manufacturer: $(device_get_manufacturer)"
    echo "Android Version: $(device_get_android_version)"
    echo "API Level: $(device_get_api_level)"
    echo "Current User: $(device_get_current_user)"
    [ -n "${USER_ID:-}" ] && echo "Selected User/Profile: $USER_ID"
    echo "Users/Profiles: $(device_get_user_count)"
    echo "Rooted: $(device_is_rooted)"
}

collect_run() {
    local output_file=$1
    shift

    local label
    label=$(basename "$output_file")

    debug "Collecting $label"

    {
        echo "# $label"
        echo "# Device: $(adb_get_serial)"
        echo "# Command: $*"
        echo "# Collected: $(date "+%Y-%m-%d %H:%M:%S %z")"
        echo
        "$@"
    } > "$output_file" 2>&1
}

collect_device_info() {
    local base_dir=${1:-.}
    local device_name
    local collection_dir
    local collection_root
    local tasks=()

    collection_root=$(output_subdir "$(output_root_dir "$base_dir")" "collections")
    mkdir -p "$collection_root"

    device_name=$(collect_safe_name "$(adb_get_serial)")
    collection_dir="$collection_root/adbgath_${device_name}_$(collect_timestamp)"
    mkdir -p "$collection_dir"

    info "Collecting device information into ${CYAN}$collection_dir${NC}"

    tasks+=("metadata.txt|collect_metadata")
    tasks+=("users.txt|adb_shell pm list users")
    tasks+=("current-user.txt|adb_shell am get-current-user")
    tasks+=("getprop.txt|adb_shell getprop")
    tasks+=("packages-all.txt|adb_shell pm list packages")
    tasks+=("packages-third-party-with-paths.txt|adb_shell pm list packages -3 -f")
    tasks+=("packages-system.txt|adb_shell pm list packages -s")
    tasks+=("apk-paths.txt|adb_get_apk_paths")
    tasks+=("permissions-and-packages.txt|adb_shell dumpsys package")
    tasks+=("battery.txt|adb_shell dumpsys battery")
    tasks+=("display.txt|adb_shell dumpsys display")
    tasks+=("connectivity.txt|adb_shell dumpsys connectivity")
    tasks+=("netstats-detail.txt|adb_shell dumpsys netstats detail")
    tasks+=("settings-global.txt|adb_shell settings list global")
    tasks+=("settings-secure.txt|adb_shell settings list secure")
    tasks+=("settings-system.txt|adb_shell settings list system")
    tasks+=("ip-addresses.txt|adb_shell ip addr show")
    tasks+=("network-interfaces.txt|adb_shell ip link show")
    tasks+=("storage.txt|adb_shell df -h")
    tasks+=("processes.txt|adb_shell ps -A")
    tasks+=("dumpsys-services.txt|adb_shell dumpsys -l")
    tasks+=("logcat-snapshot.txt|adb_command logcat -d")

    local total=${#tasks[@]}
    local current=0
    local success_count=0
    local task

    print_progress_header "ADB Collection Progress"

    for task in "${tasks[@]}"; do
        local file="${task%%|*}"
        local command="${task#*|}"

        ((current += 1))
        show_progress_bar "$current" "$total" 36 "$file"

        read -r -a command_parts <<< "$command"

        if collect_run "$collection_dir/$file" "${command_parts[@]}"; then
            ((success_count += 1))
        else
            warning "Failed to collect $file"
        fi
    done

    print_progress_footer
    success "Collection completed: $success_count/$total files"
    echo "$collection_dir"

    [ "$success_count" -eq "$total" ]
}

export -f collect_safe_name collect_timestamp collect_metadata collect_run collect_device_info

COLLECT_SOURCED=true
export COLLECT_SOURCED
