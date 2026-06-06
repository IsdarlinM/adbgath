#!/bin/bash

################################################################################
# Install Library - APK installation, uninstallation, and replacement functions
################################################################################

[[ -z "${ADB_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/adb.sh"

install_apk() {
    local apk_file=$1
    local user_id=${USER_ID:-}

    if [ ! -f "$apk_file" ]; then
        warning "APK file not found: $apk_file"
        return 1
    fi

    if [ -n "$user_id" ]; then
        info "Installing ${CYAN}$(basename "$apk_file")${NC} for user/profile ${CYAN}$user_id${NC}"
    else
        info "Installing ${CYAN}$(basename "$apk_file")${NC}"
    fi

    if adb_install_apk "$apk_file" "$user_id"; then
        success "Installed: ${CYAN}$(basename "$apk_file")${NC}"
        return 0
    fi

    warning "Failed to install: $(basename "$apk_file")"
    return 1
}

install_multiple() {
    local total=$#
    local current=0
    local success_count=0
    local apk_file

    if [ "$total" -eq 0 ]; then
        error "No APK files provided"
    fi

    info "Installing ${CYAN}$total${NC} APK(s)"
    print_progress_header "Installation Progress"

    for apk_file in "$@"; do
        ((current += 1))
        show_progress_bar "$current" "$total" 36 "$(basename "$apk_file")"

        if install_apk "$apk_file"; then
            ((success_count += 1))
        fi
    done

    print_progress_footer
    success "Installation completed: $success_count/$total successful"

    [ "$success_count" -eq "$total" ]
}

install_from_file() {
    local file=$1
    local apk_files=()

    if [ ! -f "$file" ]; then
        error "File not found: $file"
    fi

    mapfile -t apk_files < <(read_list_file "$file")

    if [ "${#apk_files[@]}" -eq 0 ]; then
        error "File is empty or contains only comments: $file"
    fi

    info "Reading APK files from ${CYAN}$file${NC}"
    install_multiple "${apk_files[@]}"
}

uninstall_package() {
    local package=$1
    local user_id=${USER_ID:-}

    if [ -z "$package" ]; then
        warning "No package specified"
        return 1
    fi

    if [ -n "$user_id" ]; then
        info "Uninstalling ${CYAN}$package${NC} from user/profile ${CYAN}$user_id${NC}"
    else
        info "Uninstalling ${CYAN}$package${NC}"
    fi

    if adb_uninstall_package "$package" "$user_id"; then
        success "Uninstalled: ${CYAN}$package${NC}"
        return 0
    fi

    warning "Failed to uninstall: $package"
    return 1
}

uninstall_multiple() {
    local total=$#
    local current=0
    local success_count=0
    local package

    if [ "$total" -eq 0 ]; then
        error "No packages provided"
    fi

    info "Uninstalling ${CYAN}$total${NC} package(s)"
    print_progress_header "Uninstallation Progress"

    for package in "$@"; do
        ((current += 1))
        show_progress_bar "$current" "$total" 36 "$package"

        if uninstall_package "$package"; then
            ((success_count += 1))
        fi
    done

    print_progress_footer
    success "Uninstallation completed: $success_count/$total successful"

    [ "$success_count" -eq "$total" ]
}

uninstall_from_file() {
    local file=$1
    local packages=()

    if [ ! -f "$file" ]; then
        error "File not found: $file"
    fi

    mapfile -t packages < <(read_list_file "$file")

    if [ "${#packages[@]}" -eq 0 ]; then
        error "File is empty or contains only comments: $file"
    fi

    info "Reading package names from ${CYAN}$file${NC}"
    uninstall_multiple "${packages[@]}"
}

replace_apk() {
    local apk_file=$1
    local package=$2
    local user_id=${USER_ID:-}

    if [ ! -f "$apk_file" ]; then
        warning "APK file not found: $apk_file"
        return 1
    fi

    if [ -z "$package" ]; then
        warning "No package name specified"
        return 1
    fi

    if [ -n "$user_id" ]; then
        info "Replacing ${CYAN}$package${NC} with ${CYAN}$(basename "$apk_file")${NC} for user/profile ${CYAN}$user_id${NC}"
    else
        info "Replacing ${CYAN}$package${NC} with ${CYAN}$(basename "$apk_file")${NC}"
    fi

    if adb_uninstall_package "$package" "$user_id"; then
        success "Removed old package: ${CYAN}$package${NC}"
    else
        warning "Old package was not uninstalled. Continuing with install: $package"
    fi

    if install_apk "$apk_file"; then
        success "Replacement completed: ${CYAN}$package${NC}"
        return 0
    fi

    warning "Replacement failed: $package"
    return 1
}

replace_pair() {
    local first=$1
    local second=$2

    if [ -f "$first" ]; then
        replace_apk "$first" "$second"
    elif [ -f "$second" ]; then
        replace_apk "$second" "$first"
    else
        warning "Invalid replacement pair. Expected APK file and package: $first $second"
        return 1
    fi
}

replace_multiple() {
    if [ "$#" -eq 0 ]; then
        error "No replacement pairs provided"
    fi

    if [ $(( $# % 2 )) -ne 0 ]; then
        error "Replacement requires pairs: APK_FILE PACKAGE_NAME"
    fi

    local total=$(( $# / 2 ))
    local current=0
    local success_count=0

    info "Replacing ${CYAN}$total${NC} package(s)"
    print_progress_header "Replacement Progress"

    while [ "$#" -gt 0 ]; do
        local first=$1
        local second=$2
        shift 2

        ((current += 1))
        show_progress_bar "$current" "$total" 36 "$first -> $second"

        if replace_pair "$first" "$second"; then
            ((success_count += 1))
        fi
    done

    print_progress_footer
    success "Replacement completed: $success_count/$total successful"

    [ "$success_count" -eq "$total" ]
}

replace_from_file() {
    local file=$1
    local args=()

    if [ ! -f "$file" ]; then
        error "File not found: $file"
    fi

    while IFS= read -r line; do
        [ -z "$line" ] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue

        local first
        local second
        first=$(echo "$line" | awk '{print $1}')
        second=$(echo "$line" | awk '{print $2}')

        if [ -z "$first" ] || [ -z "$second" ]; then
            warning "Invalid replacement line. Expected: APK_FILE PACKAGE_NAME"
            continue
        fi

        args+=("$first" "$second")
    done < "$file"

    if [ "${#args[@]}" -eq 0 ]; then
        error "File is empty or contains no valid replacement pairs: $file"
    fi

    info "Reading replacement pairs from ${CYAN}$file${NC}"
    replace_multiple "${args[@]}"
}

export -f install_apk install_multiple install_from_file
export -f uninstall_package uninstall_multiple uninstall_from_file
export -f replace_apk replace_pair replace_multiple replace_from_file

INSTALL_SOURCED=true
export INSTALL_SOURCED
