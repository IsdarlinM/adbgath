#!/usr/bin/env bash
set -Eeuo pipefail
if command -v adbgath >/dev/null 2>&1 && [[ "$(command -v adbgath)" != "${BASH_SOURCE[0]}" ]]; then
  exec adbgath "$@"
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" -m adbgath.cli "$@"
fi
printf 'adbgath is not installed. Run ./installers/linux/install.sh first.\n' >&2
exit 1
