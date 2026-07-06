#!/bin/bash

################################################################################
# JSON and Markdown reporting helpers.
################################################################################

report_write_json() {
    local output_file=$1
    local content=$2
    mkdir -p "$(dirname "$output_file")"
    printf '%s\n' "$content" > "$output_file"
}

report_write_markdown() {
    local output_file=$1
    local title=$2
    local body=$3
    mkdir -p "$(dirname "$output_file")"
    cat > "$output_file" <<EOF
# $title

$body
EOF
}

export -f report_write_json report_write_markdown

REPORTING_SOURCED=true
export REPORTING_SOURCED
