#!/bin/bash

################################################################################
# Basic defensive security posture checks for authorized Android auditing.
################################################################################

[[ -z "${ADB_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/adb.sh"
[[ -z "${CONFIG_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/config.sh"
[[ -z "${RULES_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/rules.sh"
[[ -z "${REPORTING_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/reporting.sh"

security_adb_prop() {
    local device_id=${1:-${DEVICE_ID:-}}
    local prop=$2
    if [ -z "$device_id" ] || ! command -v adb >/dev/null 2>&1; then
        echo "N/A"
        return 0
    fi
    adb -s "$device_id" shell getprop "$prop" 2>/dev/null | tr -d '\r' | head -n 1 || echo "N/A"
}

security_adb_setting() {
    local device_id=${1:-${DEVICE_ID:-}}
    local key=$2
    if [ -z "$device_id" ] || ! command -v adb >/dev/null 2>&1; then
        echo "N/A"
        return 0
    fi
    adb -s "$device_id" shell settings get global "$key" 2>/dev/null | tr -d '\r' | head -n 1 || echo "N/A"
}

security_run_checks() {
    local device_id=${1:-${DEVICE_ID:-}}
    local output_dir=${2:-$(config_get_output_dir)}
    local report_json="$output_dir/security-report.json"
    local report_md="$output_dir/security-report.md"
    local findings=""
    local patch_level
    local debuggable
    local adb_enabled
    local unknown_sources
    local selinux

    mkdir -p "$output_dir"

    patch_level=$(security_adb_prop "$device_id" ro.build.version.security_patch)
    debuggable=$(security_adb_prop "$device_id" ro.debuggable)
    adb_enabled=$(security_adb_setting "$device_id" adb_enabled)
    unknown_sources=$(security_adb_setting "$device_id" install_non_market_apps)
    selinux=$(security_adb_prop "$device_id" ro.build.selinux)

    if [ "$patch_level" = "N/A" ] || [ -z "$patch_level" ]; then
        findings+="- informational: Security patch level unavailable; evidence=property unavailable; recommendation=collect patch level from device.\n"
    else
        findings+="- informational: Security patch level detected; evidence=$patch_level; recommendation=review against supported policy.\n"
    fi

    if rule_matches_condition eq "$debuggable" "1"; then
        findings+="- high: ro.debuggable is enabled; evidence=ro.debuggable=$debuggable; recommendation=disable developer debugging for production workloads.\n"
    fi

    if rule_matches_condition eq "$adb_enabled" "1"; then
        findings+="- medium: ADB over the device settings is enabled; evidence=adb_enabled=$adb_enabled; recommendation=limit ADB exposure and review authorized access.\n"
    fi

    if rule_matches_condition eq "$unknown_sources" "1"; then
        findings+="- medium: Unknown sources are enabled; evidence=install_non_market_apps=$unknown_sources; recommendation=restrict app installation sources.\n"
    fi

    if rule_matches_condition contains "$selinux" "permissive"; then
        findings+="- medium: SELinux appears permissive; evidence=ro.build.selinux=$selinux; recommendation=verify SELinux policy enforcement.\n"
    fi

    report_write_json "$report_json" "{\"device_id\":\"$device_id\",\"findings\":[\"$findings\"]}"
    report_write_markdown "$report_md" "Security Posture Report" "$findings"

    printf '%s\n' "$findings"
    echo "$report_json"
}

export -f security_adb_prop security_adb_setting security_run_checks

SECURITY_SOURCED=true
export SECURITY_SOURCED
