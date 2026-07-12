#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_ROOT="${ADBGATH_HOME:-$HOME/.local/share/adbgath}"
BIN_ROOT="${HOME}/.local/bin"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WITH_FRIDA=true

for arg in "$@"; do
  case "$arg" in
    --skip-frida) WITH_FRIDA=false ;;
    --help|-h)
      echo "Usage: ./installers/linux/install.sh [--skip-frida]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '[adbgath] %s\n' "$*"; }
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

install_system_deps() {
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null && command -v adb >/dev/null 2>&1; then
    return
  fi
  log "Installing Python, venv support, and Android platform tools."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip adb curl unzip
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip android-tools curl unzip
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --needed python python-pip android-tools curl unzip
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper --non-interactive install python311 python311-pip android-tools curl unzip
  else
    fail "Unsupported package manager. Install Python 3.11+, python venv, and adb manually."
  fi
}

install_system_deps
command -v python3 >/dev/null 2>&1 || fail "python3 is unavailable after dependency installation."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' || fail "Python 3.11 or newer is required."

mkdir -p "$INSTALL_ROOT" "$BIN_ROOT"
if [[ ! -x "$INSTALL_ROOT/venv/bin/python" ]]; then
  log "Creating isolated Python environment."
  python3 -m venv "$INSTALL_ROOT/venv"
fi

log "Installing adbgath and web dependencies."
"$INSTALL_ROOT/venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
"$INSTALL_ROOT/venv/bin/python" -m pip install --disable-pip-version-check --upgrade "$PROJECT_ROOT"
if [[ "$WITH_FRIDA" == true ]]; then
  log "Installing optional Frida command-line tools."
  if ! "$INSTALL_ROOT/venv/bin/python" -m pip install --disable-pip-version-check --upgrade 'frida-tools>=13'; then
    printf '[WARN] Frida tools could not be installed; core CLI and web features remain available.\n' >&2
  fi
fi

cat > "$BIN_ROOT/adbgath" <<LAUNCHER
#!/usr/bin/env bash
exec "$INSTALL_ROOT/venv/bin/adbgath" "\$@"
LAUNCHER
cat > "$BIN_ROOT/adbgath-web" <<LAUNCHER
#!/usr/bin/env bash
exec "$INSTALL_ROOT/venv/bin/adbgath-web" "\$@"
LAUNCHER
chmod 0755 "$BIN_ROOT/adbgath" "$BIN_ROOT/adbgath-web"

add_path_line() {
  local file=$1
  local line='export PATH="$HOME/.local/bin:$PATH"'
  touch "$file"
  grep -Fqx "$line" "$file" || printf '\n%s\n' "$line" >> "$file"
}
add_path_line "$HOME/.profile"
[[ -f "$HOME/.bashrc" ]] && add_path_line "$HOME/.bashrc"
[[ -f "$HOME/.zshrc" ]] && add_path_line "$HOME/.zshrc"
export PATH="$BIN_ROOT:$PATH"

log "Validating installation."
adbgath --version
adb version >/dev/null
printf '\nInstallation complete. Run:\n  adbgath doctor\n  adbgath devices\n  adbgath web\n'
