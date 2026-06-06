#!/bin/bash

################################################################################
# Download Library - APK download helpers
################################################################################

[[ -z "${ADB_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/adb.sh"

download_output_path() {
    local apk_path=$1
    local output_dir=$2
    local apk_name
    local output_file

    apk_name=$(basename "$apk_path")
    output_file="$output_dir/$apk_name"

    if [ ! -e "$output_file" ]; then
        echo "$output_file"
        return 0
    fi

    local safe_name
    safe_name=$(echo "$apk_path" | sed 's#^/##; s#[/:[:space:]]#_#g')
    echo "$output_dir/$safe_name"
}

download_file_size() {
    local file=$1
    local bytes

    bytes=$(stat -c%s "$file" 2>/dev/null || wc -c < "$file" 2>/dev/null || echo "0")
    bytes=$(echo "$bytes" | awk '{print $1}')
    format_size "$bytes"
}

download_with_pv() {
    local apk_path=$1
    local output_file=$2
    local apk_name=$3
    local size=$4

    if ! command_exists pv || [ "$size" -le 0 ]; then
        return 1
    fi

    debug "Streaming with pv: $apk_path -> $output_file"
    adb_exec_out cat "$apk_path" | pv -f -p -t -e -r -b -s "$size" -N "$apk_name" > "$output_file"
}

download_single_apk() {
    local apk_path=$1
    local output_dir=${2:-.}

    if [[ ! "$apk_path" =~ ^/ ]]; then
        warning "Skipping invalid APK path: $apk_path"
        return 1
    fi

    if ! adb_file_exists "$apk_path"; then
        warning "File not found on device: $apk_path"
        return 1
    fi

    mkdir -p "$output_dir"

    local apk_name
    local output_file
    local size

    apk_name=$(basename "$apk_path")
    output_file=$(download_output_path "$apk_path" "$output_dir")
    size=$(adb_file_size "$apk_path")

    info "Downloading ${CYAN}$apk_name${NC} ($(format_size "$size"))"
    debug "Remote path: $apk_path"
    debug "Local path: $output_file"

    if download_with_pv "$apk_path" "$output_file" "$apk_name" "$size"; then
        success "Downloaded: ${CYAN}$(basename "$output_file")${NC} (${GREEN}$(download_file_size "$output_file")${NC})"
        return 0
    fi

    if adb_pull "$apk_path" "$output_file"; then
        success "Downloaded: ${CYAN}$(basename "$output_file")${NC} (${GREEN}$(download_file_size "$output_file")${NC})"
        return 0
    fi

    rm -f "$output_file"
    warning "Error downloading: $apk_path"
    return 1
}

download_multiple() {
    local output_dir=${1:-.}
    shift || true

    local apk_paths=("$@")
    local total=${#apk_paths[@]}
    local current=0
    local success_count=0
    local apk_path

    if [ "$total" -eq 0 ]; then
        error "No APK paths provided"
    fi

    mkdir -p "$output_dir"

    info "Downloading ${CYAN}$total${NC} APK(s) to ${CYAN}$output_dir${NC}"
    print_progress_header "Download Progress"

    for apk_path in "${apk_paths[@]}"; do
        ((current += 1))
        show_progress_bar "$current" "$total" 36 "$(basename "$apk_path")"

        if download_single_apk "$apk_path" "$output_dir"; then
            ((success_count += 1))
        fi
    done

    print_progress_footer
    success "Download completed: $success_count/$total successful"

    [ "$success_count" -eq "$total" ]
}

download_from_file() {
    local file=$1
    local output_dir=${2:-.}
    local apk_paths=()

    if [ ! -f "$file" ]; then
        error "File not found: $file"
    fi

    mapfile -t apk_paths < <(read_list_file "$file")

    if [ "${#apk_paths[@]}" -eq 0 ]; then
        error "File is empty or contains only comments: $file"
    fi

    info "Reading APK paths from ${CYAN}$file${NC}"
    download_multiple "$output_dir" "${apk_paths[@]}"
}

download_all_apks() {
    local output_dir=${1:-.}
    local apk_paths=()
    local user_id=${USER_ID:-}

    info "Finding APK paths on selected device..."
    mapfile -t apk_paths < <(adb_get_apk_paths "$user_id" | awk 'NF')

    if [ "${#apk_paths[@]}" -eq 0 ]; then
        warning "No APKs found on device"
        return 1
    fi

    download_multiple "$output_dir" "${apk_paths[@]}"
}

download_apk() {
    local output_dir=${OUTPUT_DIR:-.}

    if [ "$#" -eq 0 ]; then
        download_all_apks "$output_dir"
    else
        download_multiple "$output_dir" "$@"
    fi
}

export -f download_output_path download_file_size download_with_pv
export -f download_single_apk download_multiple download_from_file download_all_apks
export -f download_apk

DOWNLOAD_SOURCED=true
export DOWNLOAD_SOURCED
