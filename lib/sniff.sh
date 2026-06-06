#!/bin/bash

################################################################################
# Sniff Library - rooted tcpdump-based network capture helpers
################################################################################

[[ -z "${DEVICE_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/device.sh"

sniff_validate_duration() {
    local duration=${1:-}

    if [ -n "$duration" ] && ! [[ "$duration" =~ ^[1-9][0-9]*$ ]]; then
        error "Duration must be a positive integer number of seconds"
    fi
}

sniff_cli_name() {
    local cli="${SCRIPT_NAME:-adbgath}"

    if [[ "$cli" == *.sh ]]; then
        echo "./$cli"
    else
        echo "$cli"
    fi
}

sniff_validate_interface() {
    local interface=$1

    if ! [[ "$interface" =~ ^[A-Za-z0-9_.:-]+$ ]]; then
        error "Invalid network interface '$interface'"
    fi
}

sniff_safe_name() {
    local value=${1:-device}
    echo "$value" | sed 's/[^A-Za-z0-9._-]/_/g'
}

sniff_timestamp() {
    date "+%Y%m%d_%H%M%S"
}

sniff_output_file() {
    local output_target=${1:-.}
    local serial
    local filename
    local output_dir

    serial=$(sniff_safe_name "$(adb_get_serial)")
    filename="capture_${serial}_$(sniff_timestamp).pcap"

    if [ -z "$output_target" ] || [ "$output_target" = "." ]; then
        echo "./$filename"
        return 0
    fi

    if [ -d "$output_target" ] || [[ "$output_target" =~ [\\/]$ ]]; then
        output_dir="${output_target%/}"
        output_dir="${output_dir%\\}"
        [ -n "$output_dir" ] || output_dir="/"
        mkdir -p "$output_dir"

        if [ "$output_dir" = "/" ]; then
            echo "/$filename"
        else
            echo "$output_dir/$filename"
        fi
        return 0
    fi

    mkdir -p "$(dirname "$output_target")"
    echo "$output_target"
}

sniff_tcpdump_path() {
    adb_shell sh -c 'command -v tcpdump 2>/dev/null || ls /data/local/tmp/tcpdump /system/xbin/tcpdump /system/bin/tcpdump 2>/dev/null | head -n 1' \
        | tr -d '\r' \
        | head -n 1
}

sniff_require_tcpdump() {
    local tcpdump_path
    tcpdump_path=$(sniff_tcpdump_path || true)

    if [ -z "$tcpdump_path" ]; then
        error "tcpdump was not found on the device. Push it first: $(sniff_cli_name) --device ${DEVICE_ID:-DEVICE_ID} sniff push-tcpdump ./tcpdump"
    fi

    echo "$tcpdump_path"
}

sniff_exec_out_root() {
    local command=$1
    local uid

    uid=$(adb_shell id -u | tr -d '\r' | head -n 1 || true)

    if [ "$uid" = "0" ]; then
        adb_exec_out sh -c "$command"
    else
        adb_exec_out su -c "$command"
    fi
}

sniff_list_interfaces() {
    print_header "Network Interfaces"
    device_get_network_interfaces | while IFS= read -r iface; do
        [ -z "$iface" ] && continue
        echo -e "  ${GREEN}-${NC} $iface"
    done
}

sniff_push_tcpdump() {
    local local_file=${1:-}
    local remote_path=${2:-/data/local/tmp/tcpdump}

    if [ -z "$local_file" ]; then
        error "Missing local tcpdump binary. Usage: sniff push-tcpdump ./tcpdump [/remote/path]"
    fi

    if [ ! -f "$local_file" ]; then
        error "tcpdump binary not found: $local_file"
    fi

    info "Pushing tcpdump to ${CYAN}$remote_path${NC}"
    adb_push "$local_file" "$remote_path"
    adb_shell chmod 755 "$remote_path" >/dev/null
    success "tcpdump ready at ${CYAN}$remote_path${NC}"
}

sniff_capture() {
    local output_target=${1:-.}
    local interface=${2:-wlan0}
    local duration=${3:-}
    local output_file
    local tcpdump_path
    local command

    sniff_validate_interface "$interface"
    sniff_validate_duration "$duration"

    if ! device_has_root_access; then
        error "Network capture requires a rooted device or an accessible su binary."
    fi

    tcpdump_path=$(sniff_require_tcpdump)
    output_file=$(sniff_output_file "$output_target")
    command="$tcpdump_path -i $interface -s0 -w -"

    info "Capturing network traffic from ${CYAN}$interface${NC} to ${CYAN}$output_file${NC}"
    [ -n "$duration" ] && display_kv "Duration" "${duration}s"

    if [ -n "$duration" ]; then
        sniff_exec_out_root "$command" > "$output_file" &
        local capture_pid=$!
        sleep "$duration"
        kill "$capture_pid" >/dev/null 2>&1 || true
        wait "$capture_pid" >/dev/null 2>&1 || true
    else
        info "Press Ctrl+C to stop capture"
        sniff_exec_out_root "$command" > "$output_file"
    fi

    success "Network capture saved: ${CYAN}$output_file${NC}"
}

run_sniff_command() {
    local mode=${1:-capture}
    local output_target=${2:-.}
    shift 2 || true

    case "$mode" in
        capture|start|listen)
            sniff_capture "$output_target" "${SNIFF_INTERFACE:-wlan0}" "${SNIFF_DURATION:-}"
            ;;
        interfaces|ifaces)
            sniff_list_interfaces
            ;;
        push-tcpdump|install-tcpdump)
            sniff_push_tcpdump "${1:-}" "${2:-/data/local/tmp/tcpdump}"
            ;;
        *)
            error "Unknown sniff mode: $mode"
            ;;
    esac
}

export -f sniff_validate_duration sniff_validate_interface sniff_safe_name sniff_timestamp sniff_cli_name
export -f sniff_output_file sniff_tcpdump_path sniff_require_tcpdump sniff_exec_out_root
export -f sniff_list_interfaces sniff_push_tcpdump sniff_capture run_sniff_command

SNIFF_SOURCED=true
export SNIFF_SOURCED
