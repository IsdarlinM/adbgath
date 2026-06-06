#!/bin/bash

################################################################################
# Utility Library - logging, colors, progress bars, and common helpers
################################################################################

# Color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly MAGENTA='\033[0;35m'
readonly NC='\033[0m'

error() {
    echo -e "${RED}x Error:${NC} $*" >&2
    exit 1
}

warning() {
    echo -e "${YELLOW}! Warning:${NC} $*" >&2
}

info() {
    echo -e "${YELLOW}i${NC} $*"
}

success() {
    echo -e "${GREEN}+${NC} $*"
}

debug() {
    if [[ "${VERBOSE:-false}" == "true" ]]; then
        echo -e "${CYAN}[DEBUG]${NC} $*" >&2
    fi
}

print_header() {
    local title=$1
    echo -e "${BLUE}+-------------------------------------------------------------------+${NC}"
    printf "${BLUE}|${NC} ${CYAN}%-65s${NC} ${BLUE}|${NC}\n" "$title"
    echo -e "${BLUE}+-------------------------------------------------------------------+${NC}"
}

print_section() {
    local title=$1
    echo -e "\n${BLUE}+-- ${CYAN}${title}${NC} ${BLUE}--+${NC}"
}

print_subsection() {
    local title=$1
    echo -e "${MAGENTA}+-- $title${NC}"
}

print_separator() {
    echo -e "${BLUE}---------------------------------------------------------------------${NC}"
}

print_progress_header() {
    local title=$1
    echo -e "${BLUE}+-- ${title} --------------------------------------------------+${NC}"
}

print_progress_footer() {
    echo -e "${BLUE}+-------------------------------------------------------------------+${NC}"
}

show_progress_bar() {
    local current=$1
    local total=$2
    local width=${3:-36}
    local label=${4:-}

    if [ "$total" -le 0 ]; then
        printf "[%s] N/A %s\n" "$(printf "%${width}s" | tr ' ' '-')" "$label"
        return
    fi

    local percentage=$((current * 100 / total))
    local filled=$((percentage * width / 100))
    local empty=$((width - filled))

    printf "${CYAN}["
    printf "%${filled}s" | tr ' ' '#'
    printf "%${empty}s" | tr ' ' '-'
    printf "]${NC} %3d%% (%d/%d)" "$percentage" "$current" "$total"

    if [ -n "$label" ]; then
        printf " %s" "$label"
    fi

    printf "\n"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

var_set() {
    [[ -v "$1" && -n "${!1}" ]]
}

trim() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    echo "$value"
}

format_size() {
    local bytes=${1:-0}

    if ! [[ "$bytes" =~ ^[0-9]+$ ]]; then
        echo "N/A"
    elif ((bytes < 1024)); then
        echo "${bytes}B"
    elif ((bytes < 1048576)); then
        echo "$((bytes / 1024))KB"
    elif ((bytes < 1073741824)); then
        echo "$((bytes / 1048576))MB"
    else
        echo "$((bytes / 1073741824))GB"
    fi
}

table_row() {
    local col1=$1
    local col2=$2
    local col1_width=${3:-25}
    printf "  ${CYAN}%-${col1_width}s${NC} : %s\n" "$col1" "$col2"
}

display_kv() {
    local label=$1
    local value=$2
    printf "  ${CYAN}%-30s${NC} : ${GREEN}%s${NC}\n" "$label" "$value"
}

read_list_file() {
    local file=$1
    awk 'NF && $1 !~ /^#/ {print}' "$file"
}

export -f error warning info success debug
export -f print_header print_section print_subsection print_separator
export -f print_progress_header print_progress_footer show_progress_bar
export -f command_exists var_set trim format_size table_row display_kv read_list_file

UTILS_SOURCED=true
export UTILS_SOURCED
