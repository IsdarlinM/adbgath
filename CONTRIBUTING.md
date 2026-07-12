# Contributing

1. Create a Python 3.11+ virtual environment.
2. Install development dependencies with `python -m pip install -e ".[dev,full]"`.
3. Run `python -m ruff check src tests`.
4. Run `python -m pytest`.
5. Avoid `shell=True`, unvalidated command interpolation, arbitrary web command execution, committed binaries, secrets, target data, or generated assessment artifacts.
6. Add tests for Windows path behavior and fake-ADB output whenever a capability changes.
7. Keep CLI, web UI, README, command help, and changelog behavior aligned.
