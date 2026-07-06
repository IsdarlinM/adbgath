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

terminal_width() {
    local cols="${COLUMNS:-}"
    if [ -z "$cols" ]; then
        cols=$(tput cols 2>/dev/null || true)
    fi
    if [[ "$cols" =~ ^[0-9]+$ ]] && [ "$cols" -gt 0 ]; then
        echo "$cols"
    else
        echo 80
    fi
}

output_root_dir() {
    local requested=${1:-.}
    local root="$requested"

    if [ -z "$root" ] || [ "$root" = "." ]; then
        root="./adbgath-output"
    fi

    mkdir -p "$root"
    echo "$root"
}

output_subdir() {
    local root=$1
    local subdir=$2
    local target="$root/$subdir"

    mkdir -p "$target"
    echo "$target"
}

print_header() {
    local title=$1
    local width
    width=$(terminal_width)
    if (( width < 70 )); then
        width=70
    fi

    local border
    border=$(printf "%*s" "$width" '' | tr ' ' '-')

    echo -e "${BLUE}+${border}+${NC}"
    printf "${BLUE}|${NC} ${CYAN}%-*s${NC} ${BLUE}|${NC}\n" "$((width - 2))" "$title"
    echo -e "${BLUE}+${border}+${NC}"
}

print_section() {
    local title=$1
    echo -e "\n${BLUE}+-- ${CYAN}${title}${NC} ${BLUE}--+${NC}"
}

print_subsection() {
    local title=$1
    echo -e "${MAGENTA}+-- ${title}${NC}"
}

print_separator() {
    echo -e "${BLUE}---------------------------------------------------------------------${NC}"
}

print_progress_header() {
    local title=$1
    local width
    width=$(terminal_width)
    local padding=$((width - ${#title} - 8))

    if (( padding < 2 )); then
        padding=2
    fi

    printf "${BLUE}+-- %s" "$title"
    printf "%*s" "$padding" ''
    printf " --+${NC}\n"
}

print_progress_footer() {
    echo -e "${BLUE}+-------------------------------------------------------------------+${NC}"
}

show_progress_bar() {
    local current=$1
    local total=$2
    local width=${3:-30}
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
    local width
    width=$(terminal_width)
    local label_width=24

    if (( width > 100 )); then
        label_width=28
    elif (( width < 80 )); then
        label_width=18
    fi

    local value_width=$((width - label_width - 8))
    if (( ${#value} > value_width )); then
        value="${value:0:$((value_width - 3))}..."
    fi

    printf "  ${CYAN}%-${label_width}s${NC} : ${GREEN}%s${NC}\n" "$label" "$value"
}

read_list_file() {
    local file=$1
    awk 'NF && $1 !~ /^#/ {print}' "$file"
}

export -f error warning info success debug
export -f terminal_width output_root_dir output_subdir
export -f print_header print_section print_subsection print_separator
export -f print_progress_header print_progress_footer show_progress_bar
export -f command_exists var_set trim format_size table_row display_kv read_list_file

UTILS_SOURCED=true
export UTILS_SOURCED
