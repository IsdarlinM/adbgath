#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_ROOT="${ADBGATH_HOME:-$HOME/.local/share/adbgath}"
BIN_ROOT="$HOME/.local/bin"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WITH_FRIDA=true
WITH_BUNDLETOOL=true
PORTABLE=false
FORCE=false
OFFLINE_CACHE=""
PROXY=""

usage() {
  cat <<'EOF'
Usage: ./installers/linux/install.sh [options]

Options:
  --skip-frida             Do not install optional frida-tools.
  --skip-bundletool        Do not install optional bundletool support.
  --offline-cache DIR      Install Python wheels and optional tools from DIR.
  --proxy URL              Use this HTTPS proxy for downloads and pip.
  --install-root DIR       Override the user-scoped installation directory.
  --portable               Keep launchers inside INSTALL_ROOT/bin and do not edit shell profiles.
  --force                  Recreate the Python virtual environment.
  -h, --help               Show this help.
EOF
}

while (($#)); do
  case "$1" in
    --skip-frida) WITH_FRIDA=false; shift ;;
    --skip-bundletool) WITH_BUNDLETOOL=false; shift ;;
    --offline-cache) OFFLINE_CACHE="${2:?Missing directory for --offline-cache}"; shift 2 ;;
    --proxy) PROXY="${2:?Missing URL for --proxy}"; shift 2 ;;
    --install-root) INSTALL_ROOT="${2:?Missing directory for --install-root}"; shift 2 ;;
    --portable) PORTABLE=true; shift ;;
    --force) FORCE=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

INSTALL_ROOT="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$INSTALL_ROOT" 2>/dev/null || printf '%s' "$INSTALL_ROOT")"
if [[ -n "$OFFLINE_CACHE" ]]; then
  OFFLINE_CACHE="$(cd "$OFFLINE_CACHE" && pwd)"
  [[ -d "$OFFLINE_CACHE" ]] || { printf '[ERROR] Offline cache does not exist: %s\n' "$OFFLINE_CACHE" >&2; exit 1; }
fi
if [[ "$PORTABLE" == true ]]; then BIN_ROOT="$INSTALL_ROOT/bin"; fi

log() { printf '[adbgath] %s\n' "$*"; }
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

install_packages() {
  local packages=("$@")
  if command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y "${packages[@]}"
  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y "${packages[@]}"
  elif command -v pacman >/dev/null 2>&1; then sudo pacman -Sy --needed "${packages[@]}"
  elif command -v zypper >/dev/null 2>&1; then sudo zypper --non-interactive install "${packages[@]}"
  else fail "Unsupported package manager. Install Python 3.11+, venv support, adb, and Java manually."; fi
}

install_system_deps() {
  local python_ok=false
  command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null && python_ok=true
  if [[ "$python_ok" == true ]] && command -v adb >/dev/null 2>&1; then return; fi
  [[ -z "$OFFLINE_CACHE" ]] || fail "Python 3.11+ and adb must already be installed when using --offline-cache."
  log "Installing Python, venv support, and Android platform tools."
  if command -v apt-get >/dev/null 2>&1; then install_packages python3 python3-venv python3-pip adb curl unzip
  elif command -v dnf >/dev/null 2>&1; then install_packages python3 python3-pip android-tools curl unzip
  elif command -v pacman >/dev/null 2>&1; then install_packages python python-pip android-tools curl unzip
  elif command -v zypper >/dev/null 2>&1; then install_packages python311 python311-pip android-tools curl unzip
  fi
}

install_bundletool() {
  local tools="$INSTALL_ROOT/tools" jar="$INSTALL_ROOT/tools/bundletool.jar"
  mkdir -p "$tools"
  if [[ -f "$jar" && "$FORCE" != true ]]; then return; fi
  if ! command -v java >/dev/null 2>&1; then
    if [[ -n "$OFFLINE_CACHE" ]]; then
      printf '[WARN] Java is required for bundletool and was not found.\n' >&2
      return 0
    fi
    log "Installing a Java runtime for bundletool."
    if command -v apt-get >/dev/null 2>&1; then install_packages default-jre-headless
    elif command -v dnf >/dev/null 2>&1; then install_packages java-21-openjdk-headless
    elif command -v pacman >/dev/null 2>&1; then install_packages jre21-openjdk-headless
    elif command -v zypper >/dev/null 2>&1; then install_packages java-21-openjdk-headless
    fi
  fi
  command -v java >/dev/null 2>&1 || { printf '[WARN] Java unavailable; skipping bundletool.\n' >&2; return 0; }
  if [[ -n "$OFFLINE_CACHE" ]]; then
    [[ -f "$OFFLINE_CACHE/bundletool.jar" && -f "$OFFLINE_CACHE/bundletool.jar.sha256" ]] || fail "Offline bundletool requires bundletool.jar and bundletool.jar.sha256."
    cp "$OFFLINE_CACHE/bundletool.jar" "$jar"
    local expected actual
    expected="$(awk '{print $1; exit}' "$OFFLINE_CACHE/bundletool.jar.sha256" | tr '[:upper:]' '[:lower:]')"
    actual="$(sha256sum "$jar" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || { rm -f "$jar"; fail "Offline bundletool checksum verification failed."; }
  else
    log "Resolving the latest official Google bundletool release."
    HTTPS_PROXY="$PROXY" https_proxy="$PROXY" python3 - "$jar" <<'PY'
import hashlib, json, os, pathlib, sys, urllib.request
output = pathlib.Path(sys.argv[1])
headers = {"Accept": "application/vnd.github+json", "User-Agent": "ADB-Gath-Installer"}
request = urllib.request.Request("https://api.github.com/repos/google/bundletool/releases/latest", headers=headers)
with urllib.request.urlopen(request, timeout=30) as response:
    release = json.load(response)
asset = next((item for item in release.get("assets", []) if item.get("name", "").startswith("bundletool-all-") and item.get("name", "").endswith(".jar")), None)
if not asset:
    raise SystemExit("Official bundletool release did not include the expected JAR")
url = asset.get("browser_download_url", "")
if not url.startswith("https://github.com/google/bundletool/releases/download/"):
    raise SystemExit("Unexpected bundletool download origin")
request = urllib.request.Request(url, headers={"User-Agent": "ADB-Gath-Installer"})
with urllib.request.urlopen(request, timeout=120) as response:
    data = response.read()
digest = hashlib.sha256(data).hexdigest()
expected = str(asset.get("digest") or "")
if expected.startswith("sha256:") and digest.lower() != expected.split(":", 1)[1].lower():
    raise SystemExit("Official bundletool digest verification failed")
output.write_bytes(data)
output.with_suffix(output.suffix + ".sha256").write_text(f"{digest}  bundletool.jar\n", encoding="ascii")
PY
  fi
}

install_system_deps
command -v python3 >/dev/null 2>&1 || fail "python3 is unavailable after dependency installation."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' || fail "Python 3.11 or newer is required."
command -v adb >/dev/null 2>&1 || fail "adb is unavailable after dependency installation."

mkdir -p "$INSTALL_ROOT" "$BIN_ROOT"
if [[ "$FORCE" == true && -d "$INSTALL_ROOT/venv" ]]; then rm -rf "$INSTALL_ROOT/venv"; fi
if [[ ! -x "$INSTALL_ROOT/venv/bin/python" ]]; then
  log "Creating an isolated Python environment."
  python3 -m venv "$INSTALL_ROOT/venv"
fi

PIP_ARGS=(--disable-pip-version-check)
if [[ -n "$OFFLINE_CACHE" ]]; then PIP_ARGS+=(--no-index --find-links "$OFFLINE_CACHE"); fi
if [[ -n "$PROXY" ]]; then PIP_ARGS+=(--proxy "$PROXY"); fi
if [[ -z "$OFFLINE_CACHE" ]]; then
  "$INSTALL_ROOT/venv/bin/python" -m pip install "${PIP_ARGS[@]}" --upgrade pip setuptools wheel
fi
log "Installing adbgath and web dependencies."
"$INSTALL_ROOT/venv/bin/python" -m pip install "${PIP_ARGS[@]}" --upgrade "$PROJECT_ROOT"
if [[ "$WITH_FRIDA" == true ]]; then
  log "Installing optional Frida command-line tools."
  "$INSTALL_ROOT/venv/bin/python" -m pip install "${PIP_ARGS[@]}" --upgrade 'frida-tools>=13' || printf '[WARN] Frida tools could not be installed.\n' >&2
fi

BUNDLETOOL_JAR=""
if [[ "$WITH_BUNDLETOOL" == true ]]; then
  install_bundletool || true
  [[ -f "$INSTALL_ROOT/tools/bundletool.jar" ]] && BUNDLETOOL_JAR="$INSTALL_ROOT/tools/bundletool.jar"
fi
ADB_BINARY="$(command -v adb)"

cat > "$BIN_ROOT/adbgath" <<LAUNCHER
#!/usr/bin/env bash
export ADBGATH_HOME="$INSTALL_ROOT"
export ADB_PATH="$ADB_BINARY"
${BUNDLETOOL_JAR:+export BUNDLETOOL_JAR="$BUNDLETOOL_JAR"}
exec "$INSTALL_ROOT/venv/bin/adbgath" "\$@"
LAUNCHER
cat > "$BIN_ROOT/adbgath-web" <<LAUNCHER
#!/usr/bin/env bash
export ADBGATH_HOME="$INSTALL_ROOT"
export ADB_PATH="$ADB_BINARY"
${BUNDLETOOL_JAR:+export BUNDLETOOL_JAR="$BUNDLETOOL_JAR"}
exec "$INSTALL_ROOT/venv/bin/adbgath-web" "\$@"
LAUNCHER
chmod 0755 "$BIN_ROOT/adbgath" "$BIN_ROOT/adbgath-web"

if [[ "$PORTABLE" != true ]]; then
  add_path_line() {
    local file=$1 line='export PATH="$HOME/.local/bin:$PATH"'
    touch "$file"
    grep -Fqx "$line" "$file" || printf '\n%s\n' "$line" >> "$file"
  }
  add_path_line "$HOME/.profile"
  [[ -f "$HOME/.bashrc" ]] && add_path_line "$HOME/.bashrc"
  [[ -f "$HOME/.zshrc" ]] && add_path_line "$HOME/.zshrc"
fi
export PATH="$BIN_ROOT:$PATH"

log "Validating installation."
"$BIN_ROOT/adbgath" --version
"$ADB_BINARY" version >/dev/null
printf '\nInstallation complete.\n  CLI: %s/adbgath\n  Web: %s/adbgath-web\n' "$BIN_ROOT" "$BIN_ROOT"
if [[ "$PORTABLE" != true ]]; then printf 'Open a new shell, then run: adbgath doctor\n'; fi
