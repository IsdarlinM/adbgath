#!/usr/bin/env bash
set -Eeuo pipefail
INSTALL_ROOT="${ADBGATH_HOME:-$HOME/.local/share/adbgath}"
KEEP_WORKSPACE=false
for arg in "$@"; do
  case "$arg" in
    --keep-workspace) KEEP_WORKSPACE=true ;;
    --install-root=*) INSTALL_ROOT="${arg#*=}" ;;
    -h|--help) echo "Usage: uninstall.sh [--keep-workspace] [--install-root=DIR]"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done
rm -f "$HOME/.local/bin/adbgath" "$HOME/.local/bin/adbgath-web"
rm -rf "$INSTALL_ROOT"
if [[ "$KEEP_WORKSPACE" != true ]]; then
  rm -rf "${ADBGATH_WORKSPACE:-$HOME/adbgath-workspace}"
  if [[ -z "${ADBGATH_SERVER_HOME:-}" ]]; then
    SERVER_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/adbgath/server"
    rm -rf "$SERVER_ROOT"
  else
    printf 'Custom ADBGATH_SERVER_HOME preserved: %s\n' "$ADBGATH_SERVER_HOME"
  fi
fi
printf 'adbgath was removed.\n'
