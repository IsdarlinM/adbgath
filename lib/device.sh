#!/bin/bash

################################################################################
# Device Info Library - device information through the selected ADB target
################################################################################

[[ -z "${ADB_SOURCED:-}" ]] && source "$(dirname "${BASH_SOURCE[0]}")/adb.sh"

device_get_name() {
    local value
    value=$(adb_get_prop "ro.product.device")
    [ -n "$value" ] && [ "$value" != "N/A" ] && echo "$value" || adb_get_prop "ro.product.model"
}

device_get_model() {
    adb_get_prop "ro.product.model"
}

device_get_manufacturer() {
    adb_get_prop "ro.product.manufacturer"
}

device_get_serial() {
    adb_get_serial
}

device_get_hardware() {
    adb_get_prop "ro.hardware"
}

device_get_android_version() {
    adb_get_prop "ro.build.version.release"
}

device_get_api_level() {
    adb_get_prop "ro.build.version.sdk"
}

device_get_build_fingerprint() {
    adb_get_prop "ro.build.fingerprint"
}

device_get_build_number() {
    adb_get_prop "ro.build.display.id"
}

device_get_build_date() {
    adb_shell date "+%Y-%m-%d %H:%M:%S" | tr -d '\r' || echo "N/A"
}

device_get_kernel_version() {
    adb_shell uname -r | tr -d '\r' || echo "N/A"
}

device_get_total_ram() {
    adb_shell cat /proc/meminfo | awk '/MemTotal/ {printf "%.2f", $2 / 1024 / 1024; found=1} END {if (!found) print "N/A"}'
}

device_get_available_ram() {
    adb_shell cat /proc/meminfo | awk '/MemAvailable/ {printf "%.2f", $2 / 1024 / 1024; found=1} END {if (!found) print "N/A"}'
}

device_get_storage_info() {
    adb_shell df -h / | tail -n 1 || echo "N/A"
}

device_get_storage_total() {
    adb_shell df /data | awk 'NR == 2 {print $2; found=1} END {if (!found) print "N/A"}'
}

device_get_storage_available() {
    adb_shell df /data | awk 'NR == 2 {print $4; found=1} END {if (!found) print "N/A"}'
}

device_get_ip_address() {
    adb_shell ip addr show \
        | awk '/inet / && $2 !~ /^127\./ {split($2, ip, "/"); print ip[1]; found=1; exit} END {if (!found) print "N/A"}'
}

device_get_mac_address() {
    local mac
    mac=$(adb_shell ip link show wlan0 | awk '/link\/ether/ {print $2; exit}' || true)

    if [ -n "$mac" ]; then
        echo "$mac"
    else
        echo "N/A"
    fi
}

device_get_wifi_interface() {
    adb_shell ip link show | awk -F': ' '/^[0-9]+: wlan/ {print $2; found=1; exit} END {if (!found) print "N/A"}'
}

device_get_network_interfaces() {
    adb_shell ip link show | awk -F': ' '/^[0-9]+: / {print $2}'
}

device_get_active_network() {
    adb_shell dumpsys connectivity | grep "mCurrentDefaultNetwork" || echo "N/A"
}

device_get_wifi_status() {
    local status
    status=$(adb_shell settings get global wifi_on | tr -d '\r' || true)

    if [ "$status" = "1" ]; then
        echo "ON"
    else
        echo "OFF"
    fi
}

device_get_wifi_ssid() {
    local ssid
    ssid=$(adb_shell settings get secure wifi_ssid | tr -d '\r' | sed 's/"//g' || true)

    if [ -n "$ssid" ] && [ "$ssid" != "null" ]; then
        echo "$ssid"
    else
        echo "N/A"
    fi
}

device_get_cpu_info() {
    adb_shell cat /proc/cpuinfo | head -n 20 || echo "N/A"
}

device_get_cpu_cores() {
    adb_shell nproc | tr -d '\r' || adb_shell grep -c "^processor" /proc/cpuinfo || echo "N/A"
}

device_get_cpu_arch() {
    adb_get_prop "ro.product.cpu.abi"
}

device_get_battery_level() {
    adb_shell dumpsys battery | awk '/level/ {print $NF; found=1; exit} END {if (!found) print "N/A"}'
}

device_get_battery_status() {
    adb_shell dumpsys battery | awk '/status/ {print $NF; found=1; exit} END {if (!found) print "N/A"}'
}

device_get_battery_temperature() {
    adb_shell dumpsys battery | awk '/temperature/ {printf "%.1f", $NF / 10; found=1; exit} END {if (!found) print "N/A"}'
}

device_get_battery_health() {
    adb_shell dumpsys battery | awk '/health/ {print $NF; found=1; exit} END {if (!found) print "N/A"}'
}

device_get_package_count() {
    adb_get_packages "${USER_ID:-}" | awk 'END {print NR}'
}

device_get_users() {
    adb_get_users
}

device_get_current_user() {
    adb_get_current_user
}

device_get_user_count() {
    device_get_users | awk '/UserInfo\{/ {count += 1} END {print count + 0}'
}

device_user_exists() {
    local user_id=$1
    device_get_users | grep -Eq "UserInfo\\{${user_id}:"
}

device_get_system_apps_count() {
    local user_id=${USER_ID:-}

    if [ -n "$user_id" ]; then
        adb_shell pm list packages -s --user "$user_id" | awk 'END {print NR}'
    else
        adb_shell pm list packages -s | awk 'END {print NR}'
    fi
}

device_get_user_apps_count() {
    local user_id=${USER_ID:-}

    if [ -n "$user_id" ]; then
        adb_shell pm list packages -3 --user "$user_id" | awk 'END {print NR}'
    else
        adb_shell pm list packages -3 | awk 'END {print NR}'
    fi
}

device_get_screen_resolution() {
    adb_shell wm size | sed -n 's/^Physical size: //p' | head -n 1
}

device_get_screen_dpi() {
    adb_shell wm density | sed -n 's/^Physical density: //p' | head -n 1
}

device_get_screen_refresh_rate() {
    adb_shell dumpsys display | grep -i "refresh" || echo "N/A"
}

device_has_root_access() {
    local uid
    local su_path

    uid=$(adb_shell id -u | tr -d '\r' | head -n 1 || true)
    if [ "$uid" = "0" ]; then
        return 0
    fi

    su_path=$(adb_shell sh -c 'command -v su 2>/dev/null || ls /system/xbin/su /system/bin/su /sbin/su /su/bin/su /magisk/.core/bin/su 2>/dev/null | head -n 1' | tr -d '\r' | head -n 1 || true)
    [ -n "$su_path" ]
}

device_has_root_access_for_device() {
    local device=$1
    local uid
    local su_path

    uid=$(adb_shell_for_device "$device" id -u | tr -d '\r' | head -n 1 || true)
    if [ "$uid" = "0" ]; then
        return 0
    fi

    su_path=$(adb_shell_for_device "$device" sh -c 'command -v su 2>/dev/null || ls /system/xbin/su /system/bin/su /sbin/su /su/bin/su /magisk/.core/bin/su 2>/dev/null | head -n 1' | tr -d '\r' | head -n 1 || true)
    [ -n "$su_path" ]
}

device_is_rooted() {
    if device_has_root_access; then
        echo "Yes"
    else
        echo "No"
    fi
}

device_is_rooted_for_device() {
    local device=$1

    if device_has_root_access_for_device "$device"; then
        echo "Yes"
    else
        echo "No"
    fi
}

device_get_selinux_status() {
    adb_shell getenforce | tr -d '\r' || echo "N/A"
}

device_get_all_info() {
    debug "Gathering comprehensive device information..."

    declare -gA DEVICE_INFO=()
    DEVICE_INFO["device_name"]=$(device_get_name)
    DEVICE_INFO["model"]=$(device_get_model)
    DEVICE_INFO["manufacturer"]=$(device_get_manufacturer)
    DEVICE_INFO["serial"]=$(device_get_serial)
    DEVICE_INFO["hardware"]=$(device_get_hardware)
    DEVICE_INFO["android_version"]=$(device_get_android_version)
    DEVICE_INFO["api_level"]=$(device_get_api_level)
    DEVICE_INFO["build_number"]=$(device_get_build_number)
    DEVICE_INFO["build_date"]=$(device_get_build_date)
    DEVICE_INFO["kernel_version"]=$(device_get_kernel_version)
    DEVICE_INFO["total_ram"]=$(device_get_total_ram)
    DEVICE_INFO["available_ram"]=$(device_get_available_ram)
    DEVICE_INFO["storage_available"]=$(device_get_storage_available)
    DEVICE_INFO["storage_total"]=$(device_get_storage_total)
    DEVICE_INFO["ip_address"]=$(device_get_ip_address)
    DEVICE_INFO["mac_address"]=$(device_get_mac_address)
    DEVICE_INFO["wifi_status"]=$(device_get_wifi_status)
    DEVICE_INFO["wifi_ssid"]=$(device_get_wifi_ssid)
    DEVICE_INFO["cpu_cores"]=$(device_get_cpu_cores)
    DEVICE_INFO["cpu_arch"]=$(device_get_cpu_arch)
    DEVICE_INFO["battery_level"]=$(device_get_battery_level)
    DEVICE_INFO["battery_status"]=$(device_get_battery_status)
    DEVICE_INFO["battery_temperature"]=$(device_get_battery_temperature)
    DEVICE_INFO["current_user"]=$(device_get_current_user)
    DEVICE_INFO["user_profiles"]=$(device_get_user_count)
    DEVICE_INFO["total_packages"]=$(device_get_package_count)
    DEVICE_INFO["system_apps"]=$(device_get_system_apps_count)
    DEVICE_INFO["user_apps"]=$(device_get_user_apps_count)
    DEVICE_INFO["screen_resolution"]=$(device_get_screen_resolution)
    DEVICE_INFO["screen_dpi"]=$(device_get_screen_dpi)
    DEVICE_INFO["rooted"]=$(device_is_rooted)
    DEVICE_INFO["selinux_status"]=$(device_get_selinux_status)
}

export -f device_get_name device_get_model device_get_manufacturer device_get_serial
export -f device_get_hardware device_get_android_version device_get_api_level
export -f device_get_build_fingerprint device_get_build_number device_get_build_date
export -f device_get_kernel_version device_get_total_ram device_get_available_ram
export -f device_get_storage_info device_get_storage_total device_get_storage_available
export -f device_get_ip_address device_get_mac_address device_get_wifi_interface
export -f device_get_network_interfaces device_get_active_network device_get_wifi_status
export -f device_get_wifi_ssid device_get_cpu_info device_get_cpu_cores device_get_cpu_arch
export -f device_get_battery_level device_get_battery_status device_get_battery_temperature
export -f device_get_battery_health device_get_package_count device_get_users
export -f device_get_current_user device_get_user_count device_user_exists
export -f device_get_system_apps_count
export -f device_get_user_apps_count device_get_screen_resolution device_get_screen_dpi
export -f device_get_screen_refresh_rate device_has_root_access
export -f device_has_root_access_for_device device_is_rooted device_is_rooted_for_device
export -f device_get_selinux_status
export -f device_get_all_info

DEVICE_SOURCED=true
export DEVICE_SOURCED
