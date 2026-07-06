#!/bin/bash

################################################################################
# ADB APK Gatherer - Main Script
#
# Extract, download, install, uninstall, replace APKs, collect device data,
# monitor logs, and capture network traffic through ADB.
################################################################################

set -euo pipefail

readonly VERSION="2.2.0"
readonly SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ENV_LIB_DIR="${ADBGATH_LIB_DIR:-}"
readonly PREFIX_LIB_DIR="$SCRIPT_DIR/../lib/adbgath/lib"
readonly SYSTEM_LIB_DIR="/usr/local/lib/adbgath/lib"

if [ -n "$ENV_LIB_DIR" ]; then
    readonly LIB_DIR="$ENV_LIB_DIR"
elif [ -d "$SCRIPT_DIR/lib" ]; then
    readonly LIB_DIR="$SCRIPT_DIR/lib"
elif [ -d "$PREFIX_LIB_DIR" ]; then
    readonly LIB_DIR="$PREFIX_LIB_DIR"
elif [ -d "$SYSTEM_LIB_DIR" ]; then
    readonly LIB_DIR="$SYSTEM_LIB_DIR"
else
    readonly LIB_DIR="$SCRIPT_DIR/lib"
fi

OUTPUT_DIR="${OUTPUT_DIR:-.}"
VERBOSE="${VERBOSE:-false}"
DEVICE_ID="${DEVICE_ID:-}"
USER_ID="${USER_ID:-}"
LOG_FILTERS=()

source_required_lib() {
    local library=$1
    local path="$LIB_DIR/$library"

    if [ ! -f "$path" ]; then
        echo "Error: missing required library: $path" >&2
        exit 1
    fi

    source "$path"
}

source_optional_lib() {
    local library=$1
    local path="$LIB_DIR/$library"

    if [ -f "$path" ]; then
        source "$path"
    fi
}

source_required_lib "utils.sh"
source_required_lib "adb.sh"
source_required_lib "device.sh"
source_required_lib "download.sh"
source_required_lib "install.sh"
source_required_lib "collect.sh"
source_required_lib "list.sh"
source_required_lib "info.sh"
source_required_lib "logs.sh"
source_required_lib "sniff.sh"
source_required_lib "config.sh"
source_required_lib "discovery.sh"
source_required_lib "inventory.sh"
source_required_lib "apps_permissions.sh"
source_required_lib "findings.sh"
source_required_lib "reporting.sh"
source_required_lib "rules.sh"
source_required_lib "security.sh"
source_required_lib "doctor.sh"
source_optional_lib "app.sh"
source_optional_lib "static.sh"
source_optional_lib "runtime.sh"
source_optional_lib "proxy.sh"
source_optional_lib "backup.sh"
source_optional_lib "content.sh"
source_optional_lib "frida.sh"
source_optional_lib "mastg.sh"
source_required_lib "help.sh"

cleanup() {
    debug "Cleaning up..."
}

trap cleanup EXIT

require_feature_command() {
    local command_name=$1
    local feature_name=$2

    if ! declare -F "$command_name" >/dev/null; then
        error "$feature_name command is unavailable because its library is not installed."
    fi
}

require_action_available() {
    local action=$1

    case "$action" in
        app)
            require_feature_command "run_app_command" "app"
            ;;
        static)
            require_feature_command "run_static_command" "static"
            ;;
        runtime)
            require_feature_command "run_runtime_command" "runtime"
            ;;
        proxy)
            require_feature_command "run_proxy_command" "proxy"
            ;;
        backup)
            require_feature_command "run_backup_command" "backup"
            ;;
        content)
            require_feature_command "run_content_command" "content"
            ;;
        frida)
            require_feature_command "run_frida_command" "frida"
            ;;
        mastg)
            require_feature_command "run_mastg_command" "mastg"
            ;;
    esac
}

run_interactive_mode() {
    local script_path="$SCRIPT_DIR/$SCRIPT_NAME"
    local line

    show_help
    echo
    echo "Interactive mode. Type help for usage, version for version, or exit to quit."

    while true; do
        printf "%b" "${CYAN}adbgath>${NC} "

        if ! IFS= read -r line; then
            echo
            break
        fi

        line="$(trim "$line")"
        [ -z "$line" ] && continue

        case "$line" in
            exit|quit|q)
                break
                ;;
            help|-h|--help)
                show_help
                continue
                ;;
            version|-v|--version)
                echo "adbgath v$VERSION"
                continue
                ;;
        esac

        local command_args=()
        read -r -a command_args <<< "$line"

        if [ "${#command_args[@]}" -eq 0 ]; then
            continue
        fi

        case "${command_args[0]}" in
            adbgath|./adbgath|adbgath.sh|./adbgath.sh)
                command_args=("${command_args[@]:1}")
                ;;
        esac

        if [ "${#command_args[@]}" -eq 0 ]; then
            continue
        fi

        if ! "$BASH" "$script_path" "${command_args[@]}"; then
            warning "Command failed: $line"
        fi
    done
}

require_value() {
    local option=$1
    local value=${2:-}

    if [ -z "$value" ]; then
        error "Missing value for $option"
    fi
}

action_needs_device() {
    case "$1" in
        download|install|uninstall|replace|list|info|collect|logs|sniff|app|runtime|proxy|backup|content|frida|mastg)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

action_changes_apps() {
    case "$1" in
        install|uninstall|replace)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

require_app_change_target() {
    local action=$1

    if ! action_changes_apps "$action"; then
        return 0
    fi

    if [ -z "${DEVICE_ID:-}" ]; then
        error "$action requires an explicit device. Use --device ID or --connect IP:PORT. Run --devices to list targets."
    fi

    if [ -z "${USER_ID:-}" ]; then
        error "$action requires an explicit Android user/profile. Use --user ID, --user current, or list profiles with -l users."
    fi
}

resolve_user_selection() {
    if [ -z "${USER_ID:-}" ]; then
        return 0
    fi

    case "$USER_ID" in
        current)
            USER_ID="$(device_get_current_user)"
            ;;
        owner|primary)
            USER_ID="0"
            ;;
        *)
            if ! [[ "$USER_ID" =~ ^[0-9]+$ ]]; then
                error "Invalid user/profile '$USER_ID'. Use a numeric ID, 'current', or 'owner'."
            fi
            ;;
    esac

    if ! device_user_exists "$USER_ID"; then
        error "User/profile '$USER_ID' was not found on device '$DEVICE_ID'. Run: ./$SCRIPT_NAME --device $DEVICE_ID -l users"
    fi

    export USER_ID
    debug "Using Android user/profile: $USER_ID"
}

main() {
    if [ "$#" -eq 0 ]; then
        run_interactive_mode
        exit 0
    fi

    local action="download"
    local info_type=""
    local list_type="packages"
    local use_file=false
    local file_path=""
    local connect_target=""
    local list_devices=false
    local output_target="$OUTPUT_DIR"
    local log_mode="listen"
    local sniff_mode="capture"
    local app_mode="summary"
    local static_mode="all"
    local runtime_mode="summary"
    local proxy_mode="show"
    local backup_mode="create"
    local content_mode="providers"
    local frida_mode="ps"
    local mastg_mode="collect"
    local args=()

    TARGET_PACKAGE=""
    TARGET_APK=""
    TARGET_URI=""
    TARGET_ACTIVITY=""
    LOCAL_PATH=""
    REMOTE_PATH=""
    PROXY_SPEC=""
    PROXY_HOST=""
    PROXY_PORT=""
    LOCAL_PORT=""
    REMOTE_PORT=""
    FRIDA_SCRIPT=""
    FRIDA_EXTRA_ARGS=()
    STATIC_EXTRACT_DIR=""
    LOG_PACKAGE=""
    LOG_PID=""
    LOG_REGEX=""
    LOG_FORMAT="threadtime"
    LOG_CLEAR=false
    LOG_DURATION=""
    LOG_FILTERS=()
    SNIFF_INTERFACE="wlan0"
    SNIFF_DURATION=""

    load_config "${ADBGATH_CONFIG:-${ADBGATH_CONFIG_FILE:-./config.sh}}"

    while [ "$#" -gt 0 ]; do
        case "$1" in
            -h|--help|help)
                show_help
                exit 0
                ;;
            -v|--version|version)
                echo "adbgath v$VERSION"
                exit 0
                ;;
            --verbose)
                VERBOSE=true
                export VERBOSE
                shift
                ;;
            -D|--device|-s|--serial)
                require_value "$1" "${2:-}"
                DEVICE_ID=$2
                export DEVICE_ID
                shift 2
                ;;
            --connect)
                require_value "$1" "${2:-}"
                connect_target=$2
                shift 2
                ;;
            --devices)
                list_devices=true
                shift
                ;;
            -u|--user|--profile)
                require_value "$1" "${2:-}"
                USER_ID=$2
                export USER_ID
                shift 2
                ;;
            -o|--output)
                require_value "$1" "${2:-}"
                output_target=$2
                shift 2
                ;;
            -f|--file)
                require_value "$1" "${2:-}"
                file_path=$2
                use_file=true
                shift 2
                ;;
            -d|--download|download)
                action="download"
                shift
                ;;
            -I|--install|install)
                action="install"
                shift
                ;;
            -C|--collect|collect)
                action="collect"
                shift
                ;;
            -U|--uninstall|uninstall)
                action="uninstall"
                shift
                ;;
            -R|--replace|replace)
                action="replace"
                shift
                ;;
            logs|log|logcat)
                action="logs"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    log_mode=$1
                    shift
                fi
                ;;
            sniff|pcap|network-capture)
                action="sniff"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    sniff_mode=$1
                    shift
                fi
                ;;
            app|package)
                action="app"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    app_mode=$1
                    shift
                fi
                ;;
            static|analyze|analyse)
                action="static"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    static_mode=$1
                    shift
                fi
                ;;
            runtime|dynamic)
                action="runtime"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    runtime_mode=$1
                    shift
                fi
                ;;
            proxy|mitm)
                action="proxy"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    proxy_mode=$1
                    shift
                fi
                ;;
            backup|data)
                action="backup"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    backup_mode=$1
                    shift
                fi
                ;;
            content|provider|providers)
                action="content"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    content_mode=$1
                    shift
                fi
                ;;
            frida|instrument)
                action="frida"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    frida_mode=$1
                    shift
                fi
                ;;
            mastg|owasp|audit)
                action="mastg"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    mastg_mode=$1
                    shift
                fi
                ;;
            -l|--list|list)
                action="list"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    list_type=$1
                    shift
                fi
                ;;
            inventory)
                action="inventory"
                shift
                ;;
            security)
                action="security"
                shift
                ;;
            apps)
                action="apps"
                shift
                ;;
            report)
                action="report"
                shift
                ;;
            doctor)
                action="doctor"
                shift
                ;;
            -i|--info|info)
                action="info"
                shift
                if [ "$#" -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                    info_type=$1
                    shift
                fi
                ;;
            --package)
                require_value "$1" "${2:-}"
                TARGET_PACKAGE=$2
                LOG_PACKAGE=$2
                shift 2
                ;;
            --apk)
                require_value "$1" "${2:-}"
                TARGET_APK=$2
                shift 2
                ;;
            --uri)
                require_value "$1" "${2:-}"
                TARGET_URI=$2
                shift 2
                ;;
            --activity)
                require_value "$1" "${2:-}"
                TARGET_ACTIVITY=$2
                shift 2
                ;;
            --local)
                require_value "$1" "${2:-}"
                LOCAL_PATH=$2
                shift 2
                ;;
            --remote)
                require_value "$1" "${2:-}"
                REMOTE_PATH=$2
                shift 2
                ;;
            --proxy)
                require_value "$1" "${2:-}"
                PROXY_SPEC=$2
                shift 2
                ;;
            --proxy-host)
                require_value "$1" "${2:-}"
                PROXY_HOST=$2
                shift 2
                ;;
            --proxy-port)
                require_value "$1" "${2:-}"
                PROXY_PORT=$2
                shift 2
                ;;
            --local-port)
                require_value "$1" "${2:-}"
                LOCAL_PORT=$2
                shift 2
                ;;
            --remote-port)
                require_value "$1" "${2:-}"
                REMOTE_PORT=$2
                shift 2
                ;;
            --script)
                require_value "$1" "${2:-}"
                FRIDA_SCRIPT=$2
                shift 2
                ;;
            --extract-dir)
                require_value "$1" "${2:-}"
                STATIC_EXTRACT_DIR=$2
                shift 2
                ;;
            --pid)
                require_value "$1" "${2:-}"
                LOG_PID=$2
                shift 2
                ;;
            --regex|--grep)
                require_value "$1" "${2:-}"
                LOG_REGEX=$2
                shift 2
                ;;
            --format)
                require_value "$1" "${2:-}"
                LOG_FORMAT=$2
                shift 2
                ;;
            --filter)
                require_value "$1" "${2:-}"
                LOG_FILTERS+=("$2")
                shift 2
                ;;
            --clear-logs)
                LOG_CLEAR=true
                shift
                ;;
            --duration|--seconds)
                require_value "$1" "${2:-}"
                LOG_DURATION=$2
                SNIFF_DURATION=$2
                shift 2
                ;;
            --interface|--iface)
                require_value "$1" "${2:-}"
                SNIFF_INTERFACE=$2
                shift 2
                ;;
            --)
                shift
                args+=("$@")
                break
                ;;
            -*)
                error "Unknown option: $1"
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done

    OUTPUT_DIR="$output_target"
    LOG_MODE="$log_mode"
    SNIFF_MODE="$sniff_mode"
    export OUTPUT_DIR TARGET_PACKAGE TARGET_APK TARGET_URI TARGET_ACTIVITY LOCAL_PATH REMOTE_PATH
    export PROXY_SPEC PROXY_HOST PROXY_PORT LOCAL_PORT REMOTE_PORT FRIDA_SCRIPT STATIC_EXTRACT_DIR
    export LOG_PACKAGE LOG_PID LOG_REGEX LOG_FORMAT LOG_CLEAR LOG_DURATION
    export SNIFF_INTERFACE SNIFF_DURATION

    require_action_available "$action"

    if action_needs_device "$action" || [ -n "$connect_target" ] || [ "$list_devices" = true ]; then
        adb_check_installed
    fi

    if [ -n "$connect_target" ]; then
        adb_connect_device "$connect_target"
    fi

    if [ "$list_devices" = true ]; then
        show_available_devices
        exit 0
    fi

    require_app_change_target "$action"

    if action_needs_device "$action"; then
        adb_check_device
        resolve_user_selection
    fi

    case "$action" in
        download)
            if [ "$use_file" = true ]; then
                download_from_file "$file_path" "$output_target"
            elif [ "${#args[@]}" -gt 0 ]; then
                download_multiple "$output_target" "${args[@]}"
            else
                download_all_apks "$output_target"
            fi
            ;;
        install)
            if [ "$use_file" = true ]; then
                install_from_file "$file_path"
            elif [ "${#args[@]}" -gt 0 ]; then
                install_multiple "${args[@]}"
            else
                error "No APK file specified for installation"
            fi
            ;;
        uninstall)
            if [ "$use_file" = true ]; then
                uninstall_from_file "$file_path"
            elif [ "${#args[@]}" -gt 0 ]; then
                uninstall_multiple "${args[@]}"
            else
                error "No package name specified for uninstallation"
            fi
            ;;
        replace)
            if [ "$use_file" = true ]; then
                replace_from_file "$file_path"
            elif [ "${#args[@]}" -gt 0 ]; then
                replace_multiple "${args[@]}"
            else
                error "No replacement pair specified"
            fi
            ;;
        list)
            run_list_command "$list_type"
            ;;
        info)
            run_info_command "$info_type"
            ;;
        inventory)
            inventory_basic "$DEVICE_ID" "$output_target"
            ;;
        security)
            security_run_checks "$DEVICE_ID" "$output_target"
            ;;
        apps)
            apps_list_packages "$DEVICE_ID"
            ;;
        report)
            report_write_markdown "$output_target/report.md" "ADB Audit Report" "Report generation is enabled."
            ;;
        doctor)
            doctor_check "$output_target"
            ;;
        collect)
            collect_device_info "$output_target"
            ;;
        logs)
            if [ "${#args[@]}" -gt 0 ]; then
                LOG_FILTERS+=("${args[@]}")
            fi
            run_logs_command "$LOG_MODE" "$output_target"
            ;;
        sniff)
            run_sniff_command "$SNIFF_MODE" "$output_target" "${args[@]}"
            ;;
        app)
            run_app_command "$app_mode" "${args[@]}"
            ;;
        static)
            run_static_command "$static_mode" "$output_target" "${args[@]}"
            ;;
        runtime)
            run_runtime_command "$runtime_mode" "$output_target" "${args[@]}"
            ;;
        proxy)
            run_proxy_command "$proxy_mode" "${args[@]}"
            ;;
        backup)
            run_backup_command "$backup_mode" "$output_target" "${args[@]}"
            ;;
        content)
            run_content_command "$content_mode" "$output_target" "${args[@]}"
            ;;
        frida)
            run_frida_command "$frida_mode" "${args[@]}"
            ;;
        mastg)
            run_mastg_command "$mastg_mode" "$output_target" "${args[@]}"
            ;;
        *)
            error "Unknown action: $action"
            ;;
    esac
}

main "$@"
