#!/bin/bash

################################################################################
# Info Library - formatted Android device information
################################################################################

[[ -z "${LIST_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/list.sh"

show_device_basic_info() {
    print_header "Basic Device Information"
    display_kv "Selected Device" "$(adb_get_serial)"
    display_kv "Connection Type" "$(adb_get_connection_type)"
    display_kv "Device Name" "$(device_get_name)"
    display_kv "Model" "$(device_get_model)"
    display_kv "Manufacturer" "$(device_get_manufacturer)"
    display_kv "Hardware" "$(device_get_hardware)"
    print_separator
}

show_device_os_info() {
    print_section "OS and Build Information"
    display_kv "Android Version" "$(device_get_android_version)"
    display_kv "API Level" "$(device_get_api_level)"
    display_kv "Build Number" "$(device_get_build_number)"
    display_kv "Build Date" "$(device_get_build_date)"
    display_kv "Kernel Version" "$(device_get_kernel_version)"
    print_separator
}

show_device_hardware_info() {
    print_section "Hardware Information"
    display_kv "CPU Cores" "$(device_get_cpu_cores)"
    display_kv "CPU Architecture" "$(device_get_cpu_arch)"
    display_kv "Total RAM" "$(device_get_total_ram) GB"
    display_kv "Available RAM" "$(device_get_available_ram) GB"
    echo ""
    print_subsection "Storage"
    display_kv "Total Storage" "$(device_get_storage_total) KB"
    display_kv "Available Storage" "$(device_get_storage_available) KB"
    print_separator
}

show_device_network_info() {
    print_section "Network Information"
    display_kv "IP Address" "$(device_get_ip_address)"
    display_kv "MAC Address" "$(device_get_mac_address)"
    display_kv "WiFi Interface" "$(device_get_wifi_interface)"
    display_kv "WiFi Status" "$(device_get_wifi_status)"
    display_kv "WiFi SSID" "$(device_get_wifi_ssid)"

    echo ""
    print_subsection "Available Interfaces"
    device_get_network_interfaces | while IFS= read -r iface; do
        [ -z "$iface" ] && continue
        echo -e "  ${GREEN}-${NC} $iface"
    done

    print_separator
}

show_device_battery_info() {
    print_section "Battery Information"
    display_kv "Battery Level" "$(device_get_battery_level)%"
    display_kv "Battery Status" "$(device_get_battery_status)"
    display_kv "Temperature" "$(device_get_battery_temperature) C"
    display_kv "Health" "$(device_get_battery_health)"
    print_separator
}

show_device_screen_info() {
    print_section "Screen Information"
    display_kv "Resolution" "$(device_get_screen_resolution)"
    display_kv "DPI" "$(device_get_screen_dpi)"
    print_separator
}

show_device_app_info() {
    print_section "Application Information"
    display_kv "Users/Profiles" "$(device_get_user_count)"
    display_kv "Current User" "$(device_get_current_user)"
    [ -n "${USER_ID:-}" ] && display_kv "Selected User/Profile" "$USER_ID"
    display_kv "Total Packages" "$(device_get_package_count)"
    display_kv "System Apps" "$(device_get_system_apps_count)"
    display_kv "User Apps" "$(device_get_user_apps_count)"
    print_separator
}

show_device_users_info() {
    print_section "Users and Profiles"
    list_device_users
    print_separator
}

show_device_security_info() {
    print_section "Security Information"
    display_kv "Rooted" "$(device_is_rooted)"
    display_kv "SELinux Status" "$(device_get_selinux_status)"
    display_kv "Current UID" "$(adb_shell id -u | tr -d '\r' || echo 'N/A')"
    display_kv "Shell Context" "$(adb_shell id | tr -d '\r' || echo 'N/A')"
    print_separator
}

show_device_all_info() {
    print_header "Complete Device Information"
    show_device_basic_info
    show_device_os_info
    show_device_hardware_info
    show_device_network_info
    show_device_battery_info
    show_device_screen_info
    show_device_app_info
    show_device_users_info
    show_device_security_info
    success "Device information gathering complete"
}

run_info_command() {
    local info_type=${1:-}

    case "$info_type" in
        basic)
            show_device_basic_info
            ;;
        os)
            show_device_os_info
            ;;
        hardware|hw)
            show_device_hardware_info
            ;;
        network|net)
            show_device_network_info
            ;;
        battery)
            show_device_battery_info
            ;;
        screen)
            show_device_screen_info
            ;;
        apps|packages)
            show_device_app_info
            ;;
        users|user|profiles|profile)
            show_device_users_info
            ;;
        security)
            show_device_security_info
            ;;
        "")
            show_device_all_info
            ;;
        *)
            error "Unknown info type: $info_type"
            ;;
    esac
}

export -f show_device_basic_info show_device_os_info show_device_hardware_info
export -f show_device_network_info show_device_battery_info show_device_screen_info
export -f show_device_app_info show_device_users_info show_device_security_info
export -f show_device_all_info run_info_command

INFO_SOURCED=true
export INFO_SOURCED
