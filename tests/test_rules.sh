#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$ROOT_DIR/lib/rules.sh"

assert_success() {
    if ! "$@"; then
        echo "expected success for: $*" >&2
        exit 1
    fi
}

assert_failure() {
    if "$@"; then
        echo "expected failure for: $*" >&2
        exit 1
    fi
}

assert_success rule_matches_condition eq 1 1
assert_failure rule_matches_condition eq 1 0
assert_success rule_matches_condition contains "adb enabled" enabled
assert_failure rule_matches_condition contains "adb enabled" disabled

echo "Rules engine smoke tests passed"
