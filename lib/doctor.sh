#!/bin/bash

################################################################################
# Environment health checks for the defensive ADB toolchain.
################################################################################

[[ -z "${CONFIG_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

doctor_check() {
    local output_dir=${1:-$(config_get_output_dir)}
    mkdir -p "$output_dir"

    local issues=0
    if ! command -v adb >/dev/null 2>&1; then
        echo "ADB not found in PATH"
        issues=$((issues + 1))
    else
        echo "ADB found: $(command -v adb)"
    fi

    if ! command -v bash >/dev/null 2>&1; then
        echo "Bash not found"
        issues=$((issues + 1))
    fi

    echo "Output dir: $output_dir"
    echo "Doctor checks completed with $issues issues"
}

export -f doctor_check

DOCTOR_SOURCED=true
export DOCTOR_SOURCED
