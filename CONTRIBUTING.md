# Contributing

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
node --check src/adbgath/web/static/app.js
python -m build
```

## Requirements

- Keep host subprocess execution as argument arrays with `shell=False`.
- Add operations to the shared catalog rather than creating CLI-only or web-only logic.
- Validate all device identifiers, package names, profiles, paths, ports, durations, and network values.
- Mark state-changing web operations as destructive.
- Add tests for Windows paths, spaces, Unicode, failures, cancellation boundaries, and ADB offline/unauthorized states where applicable.
- Do not commit executables, APKs, JARs, PCAPs, generated reports, virtual environments, or build output.
- Keep documentation and `CHANGELOG.md` synchronized with behavior.

## Branding protection

The existing ADB-Gath logo, name, banner, colors, developer attribution, and visual identity must not be changed without explicit project-owner authorization. `tests/test_branding.py` intentionally protects the approved banner and web identity.

## Security extensions

Plugins and Frida scripts must be suitable for authorized defensive assessment. Do not add credential theft, persistence, evasion, exfiltration, destructive automation, or hidden behavior.
