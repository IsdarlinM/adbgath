#!/bin/bash

################################################################################
# List Library - devices, packages, APK paths, and Android users/profiles
################################################################################

[[ -z "${DEVICE_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/device.sh"

show_available_devices() {
    print_header "Connected Devices"

    local devices
    devices=$(adb_list_devices_detailed || true)

    if [ -z "$devices" ]; then
        warning "No devices found"
        return 1
    fi

    printf "  %-4s %-24s %-10s %-12s %-12s %s\n" "Mark" "Device ID" "Type" "State" "Root" "Model"
    print_separator

    local count=0
    local line

    while IFS= read -r line; do
        [ -z "$line" ] && continue
        ((count += 1))

        local device_id
        local state
        local connection_type
        local model
        local mark
        local root_label

        device_id=$(echo "$line" | awk '{print $1}')
        state=$(adb_get_device_state "$device_id")
        connection_type=$(adb_get_connection_type "$device_id")
        model=$(adb_get_prop_for_device "$device_id" "ro.product.model" || true)
        [ -n "$model" ] || model="N/A"

        if device_has_root_access_for_device "$device_id"; then
            mark="${GREEN}r${NC}"
            root_label="${GREEN}rooted${NC}"
        else
            mark="${YELLOW}i${NC}"
            root_label="${YELLOW}not-rooted${NC}"
        fi

        printf "  %b    ${CYAN}%-24s${NC} %-10s %-12s " \
            "$mark" "$device_id" "$connection_type" "$state"
        printf "%b" "$root_label"
        printf " %s\n" "$model"
    done <<< "$devices"

    echo ""
    echo -e "  ${GREEN}r${NC} = relevant/rooted, ${YELLOW}i${NC} = irrelevant/non-rooted"
    success "Total devices: $count"
}

list_packages() {
    print_header "Installed Packages"

    local user_id=${USER_ID:-}
    local packages
    packages=$(adb_get_packages "$user_id" || true)

    if [ -z "$packages" ]; then
        warning "No packages found"
        return 1
    fi

    if [ -n "$user_id" ]; then
        display_kv "User/Profile" "$user_id"
        print_separator
    fi

    local count=0
    local package

    while IFS= read -r package; do
        [ -z "$package" ] && continue
        ((count += 1))
        echo -e "${GREEN}[$count]${NC} $package"
    done <<< "$packages"

    echo ""
    success "Total packages: $count"
}

list_apk_paths() {
    print_header "APK Paths"

    local user_id=${USER_ID:-}
    local paths
    paths=$(adb_get_apk_paths "$user_id" || true)

    if [ -z "$paths" ]; then
        warning "No APK paths found"
        return 1
    fi

    if [ -n "$user_id" ]; then
        display_kv "User/Profile" "$user_id"
        print_separator
    fi

    local count=0
    local apk_path

    while IFS= read -r apk_path; do
        [ -z "$apk_path" ] && continue
        ((count += 1))
        echo -e "${GREEN}[$count]${NC} $apk_path"
    done <<< "$paths"

    echo ""
    success "Total APKs: $count"
}

list_device_users() {
    print_header "Device Users and Profiles"

    local users
    users=$(device_get_users || true)

    if [ -z "$users" ]; then
        warning "No users or profiles found"
        return 1
    fi

    local current_user
    current_user=$(device_get_current_user)

    local count=0
    local line

    while IFS= read -r line; do
        [ -z "$line" ] && continue

        if [[ "$line" =~ UserInfo\{([0-9]+):([^:}]+):([^}]*)\}[[:space:]]*(.*) ]]; then
            local user_id="${BASH_REMATCH[1]}"
            local user_name="${BASH_REMATCH[2]}"
            local flags="${BASH_REMATCH[3]}"
            local state="${BASH_REMATCH[4]:-}"
            local marker=""

            [ "$user_id" = "$current_user" ] && marker=" current"
            ((count += 1))

            printf "${GREEN}[%d]${NC} id=%-4s name=%-24s flags=%-12s state=%s%s\n" \
                "$count" "$user_id" "$user_name" "$flags" "${state:-N/A}" "$marker"
        else
            echo "$line"
        fi
    done <<< "$users"

    echo ""
    display_kv "Current User" "$current_user"
    success "Total users/profiles: $count"
}

run_list_command() {
    local list_type=${1:-packages}

    case "$list_type" in
        packages|pkg|"")
            list_packages
            ;;
        paths|path|apk|apks)
            list_apk_paths
            ;;
        users|user|profiles|profile)
            list_device_users
            ;;
        devices|device)
            show_available_devices
            ;;
        *)
            error "Unknown list type: $list_type"
            ;;
    esac
}

export -f show_available_devices list_packages list_apk_paths list_device_users
export -f run_list_command

LIST_SOURCED=true
export LIST_SOURCED
