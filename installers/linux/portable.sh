#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTINATION="${1:-$SCRIPT_DIR/../../portable-adbgath}"
shift || true
exec "$SCRIPT_DIR/install.sh" --portable --install-root "$DESTINATION" "$@"
