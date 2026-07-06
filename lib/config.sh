#!/bin/bash

################################################################################
# Configuration helpers for defensive Android ADB auditing.
################################################################################

CONFIG_FILE="${ADBGATH_CONFIG:-${ADBGATH_CONFIG_FILE:-./config.sh}}"
ADBGATH_OUTPUT_DIR="${ADBGATH_OUTPUT_DIR:-${OUTPUT_DIR:-./adbgath-output}}"
ADBGATH_TIMEOUT="${ADBGATH_TIMEOUT:-10}"
ADBGATH_REDACT="${ADBGATH_REDACT:-true}"
ADBGATH_NO_SENSITIVE="${ADBGATH_NO_SENSITIVE:-false}"
ADBGATH_PARALLEL="${ADBGATH_PARALLEL:-1}"

load_config() {
    local config_path="${1:-$CONFIG_FILE}"
    if [ -f "$config_path" ]; then
        # shellcheck disable=SC1090
        source "$config_path"
    fi

    ADDBGATH_OUTPUT_DIR="${ADBGATH_OUTPUT_DIR:-${OUTPUT_DIR:-./adbgath-output}}"
    ADDBGATH_TIMEOUT="${ADBGATH_TIMEOUT:-10}"
    ADDBGATH_REDACT="${ADBGATH_REDACT:-true}"
    ADDBGATH_NO_SENSITIVE="${ADDBGATH_NO_SENSITIVE:-false}"
    ADDBGATH_PARALLEL="${ADDBGATH_PARALLEL:-1}"

    export ADDBGATH_OUTPUT_DIR ADDBGATH_TIMEOUT ADDBGATH_REDACT ADDBGATH_NO_SENSITIVE ADDBGATH_PARALLEL
}

config_get_output_dir() {
    echo "${ADDBGATH_OUTPUT_DIR:-./adbgath-output}"
}

config_is_redaction_enabled() {
    [[ "${ADDBGATH_REDACT:-true}" == "true" ]]
}

config_is_sensitive_redaction_forced() {
    [[ "${ADDBGATH_NO_SENSITIVE:-false}" == "true" ]]
}

export -f load_config config_get_output_dir config_is_redaction_enabled config_is_sensitive_redaction_forced

CONFIG_SOURCED=true
export CONFIG_SOURCED
