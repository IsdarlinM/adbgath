#!/bin/bash

################################################################################
# Lightweight rules engine for defensive findings.
################################################################################

rule_matches_condition() {
    local operator=$1
    local left=$2
    local right=$3
    case "$operator" in
        eq) [[ "$left" == "$right" ]] ;;
        contains) [[ "$left" == *"$right"* ]] ;;
        gt) [[ "$left" -gt "$right" ]] ;;
        lt) [[ "$left" -lt "$right" ]] ;;
        *) return 1 ;;
    esac
}

rule_evaluate() {
    local rule_id=$1
    local operator=$2
    local left=$3
    local right=$4
    local severity=${5:-informational}
    local description=${6:-rule}
    local recommendation=${7:-review}

    if rule_matches_condition "$operator" "$left" "$right"; then
        printf '%s\t%s\t%s\t%s\t%s\n' "$severity" "$rule_id" "$description" "$recommendation" "$left"
        return 0
    fi

    return 1
}

export -f rule_matches_condition rule_evaluate

RULES_SOURCED=true
export RULES_SOURCED
