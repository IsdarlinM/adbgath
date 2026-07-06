#!/bin/bash

################################################################################
# Defensive findings and risk scoring helpers.
################################################################################

[[ -z "${CONFIG_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

findings_add() {
    local severity=${1:-informational}
    local title=${2:-finding}
    local evidence=${3:-}
    local recommendation=${4:-N/A}

    printf '%s\t%s\t%s\t%s\n' "$severity" "$title" "$evidence" "$recommendation"
}

findings_score() {
    local severity=$1
    case "$severity" in
        critical) echo 4 ;;
        high) echo 3 ;;
        medium) echo 2 ;;
        low) echo 1 ;;
        *) echo 0 ;;
    esac
}

export -f findings_add findings_score

FINDINGS_SOURCED=true
export FINDINGS_SOURCED
