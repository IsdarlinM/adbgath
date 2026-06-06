#!/bin/bash

################################################################################
# Logs Library - Android logcat listening and capture helpers
################################################################################

[[ -z "${ADB_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/adb.sh"

LOGCAT_ARGS=()

logs_validate_duration() {
    local duration=${1:-}

    if [ -n "$duration" ] && ! [[ "$duration" =~ ^[1-9][0-9]*$ ]]; then
        error "Duration must be a positive integer number of seconds"
    fi
}

logs_safe_name() {
    local value=${1:-device}
    echo "$value" | sed 's/[^A-Za-z0-9._-]/_/g'
}

logs_timestamp() {
    date "+%Y%m%d_%H%M%S"
}

logs_output_file() {
    local output_target=${1:-.}
    local serial
    local filename
    local output_dir

    serial=$(logs_safe_name "$(adb_get_serial)")
    filename="logcat_${serial}_$(logs_timestamp).log"

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

logs_get_package_pid() {
    local package=$1
    local pid

    pid=$(adb_shell pidof "$package" | tr -d '\r' | awk '{print $1}' || true)

    if [ -z "$pid" ]; then
        pid=$(adb_shell ps -A | awk -v pkg="$package" '$NF == pkg {print $2; exit}' || true)
    fi

    echo "$pid"
}

logs_prepare_args() {
    local format=${LOG_FORMAT:-threadtime}
    local pid=${LOG_PID:-}

    logs_validate_duration "${LOG_DURATION:-}"

    if [ "${LOG_CLEAR:-false}" = true ]; then
        info "Clearing logcat buffer before starting"
        adb_command logcat -c
    fi

    if [ -n "${LOG_PACKAGE:-}" ]; then
        pid=$(logs_get_package_pid "$LOG_PACKAGE")

        if [ -z "$pid" ]; then
            error "Package '$LOG_PACKAGE' is not running. Start the app or pass --pid PID."
        fi

        debug "Resolved package '$LOG_PACKAGE' to PID '$pid'"
    fi

    LOGCAT_ARGS=(-v "$format")

    if [ -n "$pid" ]; then
        LOGCAT_ARGS+=(--pid "$pid")
    fi

    if [ -n "${LOG_REGEX:-}" ]; then
        LOGCAT_ARGS+=(-e "$LOG_REGEX")
    fi

    if declare -p LOG_FILTERS >/dev/null 2>&1 && [ "${#LOG_FILTERS[@]}" -gt 0 ]; then
        LOGCAT_ARGS+=("${LOG_FILTERS[@]}")
    fi
}

logs_listen() {
    logs_prepare_args

    info "Listening to logcat on ${CYAN}$(adb_get_serial)${NC}"
    [ -n "${LOG_PACKAGE:-}" ] && display_kv "Package" "$LOG_PACKAGE"
    [ -n "${LOG_PID:-}" ] && display_kv "PID" "$LOG_PID"
    [ -n "${LOG_REGEX:-}" ] && display_kv "Regex" "$LOG_REGEX"
    [ -n "${LOG_DURATION:-}" ] && display_kv "Duration" "${LOG_DURATION}s"

    if [ -n "${LOG_DURATION:-}" ]; then
        adb_command logcat "${LOGCAT_ARGS[@]}" &
        local log_pid=$!
        sleep "$LOG_DURATION"
        kill "$log_pid" >/dev/null 2>&1 || true
        wait "$log_pid" >/dev/null 2>&1 || true
        success "Log listening finished"
        return 0
    fi

    adb_command logcat "${LOGCAT_ARGS[@]}"
}

logs_capture() {
    local output_target=${1:-.}
    local output_file

    output_file=$(logs_output_file "$output_target")
    logs_prepare_args

    info "Capturing logcat to ${CYAN}$output_file${NC}"
    [ -n "${LOG_PACKAGE:-}" ] && display_kv "Package" "$LOG_PACKAGE"
    [ -n "${LOG_PID:-}" ] && display_kv "PID" "$LOG_PID"
    [ -n "${LOG_REGEX:-}" ] && display_kv "Regex" "$LOG_REGEX"

    if [ -n "${LOG_DURATION:-}" ]; then
        display_kv "Duration" "${LOG_DURATION}s"
        adb_command logcat "${LOGCAT_ARGS[@]}" > "$output_file" &
        local log_pid=$!
        sleep "$LOG_DURATION"
        kill "$log_pid" >/dev/null 2>&1 || true
        wait "$log_pid" >/dev/null 2>&1 || true
    else
        info "Press Ctrl+C to stop capture"
        adb_command logcat "${LOGCAT_ARGS[@]}" > "$output_file"
    fi

    success "Log capture saved: ${CYAN}$output_file${NC}"
}

logs_clear() {
    adb_command logcat -c
    success "Logcat buffer cleared on ${CYAN}$(adb_get_serial)${NC}"
}

run_logs_command() {
    local mode=${1:-listen}
    local output_target=${2:-.}

    case "$mode" in
        listen|tail|watch)
            logs_listen
            ;;
        capture|save|dump)
            logs_capture "$output_target"
            ;;
        clear|clean)
            logs_clear
            ;;
        *)
            error "Unknown logs mode: $mode"
            ;;
    esac
}

export -f logs_validate_duration logs_safe_name logs_timestamp logs_output_file
export -f logs_get_package_pid logs_prepare_args logs_listen logs_capture logs_clear
export -f run_logs_command

LOGS_SOURCED=true
export LOGS_SOURCED
