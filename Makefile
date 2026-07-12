.PHONY: help install install-full uninstall test lint web clean version

PYTHON ?= python3

help:
	@echo "adbgath development targets"
	@echo "  make install       Install editable package"
	@echo "  make install-full  Install with Frida tooling"
	@echo "  make test          Run the automated test suite"
	@echo "  make lint          Run Ruff and compile checks"
	@echo "  make web           Start the local web UI"

install:
	$(PYTHON) -m pip install -e .

install-full:
	$(PYTHON) -m pip install -e '.[full,dev]'

uninstall:
	$(PYTHON) -m pip uninstall -y adbgath

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m compileall -q src

web:
	$(PYTHON) -m adbgath.cli web

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov build dist *.egg-info src/*.egg-info

version:
	@$(PYTHON) -c 'from adbgath import __version__; print(__version__)'
