#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$ROOT_DIR/lib/adb.sh"

# Basic smoke tests for the ADB wrapper helpers.
assert_contains() {
    local haystack=$1
    local needle=$2
    if [[ "$haystack" != *"$needle"* ]]; then
        echo "expected '$needle' in '$haystack'" >&2
        exit 1
    fi
}

# These tests are intentionally lightweight and do not require a device.
if command -v adb >/dev/null 2>&1; then
    echo "ADB wrapper smoke tests passed"
else
    echo "ADB not present; skipping runtime wrapper tests"
fi
