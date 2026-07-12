#!/usr/bin/env bash
set -Eeuo pipefail
INSTALL_ROOT="${ADBGATH_HOME:-$HOME/.local/share/adbgath}"
rm -rf "$INSTALL_ROOT"
rm -f "$HOME/.local/bin/adbgath" "$HOME/.local/bin/adbgath-web"
if [[ "${1:-}" != "--keep-workspace" ]]; then
  rm -rf "$HOME/adbgath-workspace"
fi
echo "adbgath removed. PATH entries are intentionally left intact because ~/.local/bin may contain other tools."
