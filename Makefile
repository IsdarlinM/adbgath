.PHONY: help install uninstall test lint format clean version

SCRIPT := adbgath.sh
VERSION := 2.2.0
INSTALL_PATH := /usr/local/bin/adbgath
LIB_INSTALL_DIR := /usr/local/lib/adbgath
LIBS := lib/utils.sh lib/adb.sh lib/device.sh lib/download.sh lib/install.sh lib/collect.sh lib/list.sh lib/info.sh lib/logs.sh lib/sniff.sh lib/help.sh

help:
	@echo "adbgath - Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  make install    - Install script to $(INSTALL_PATH)"
	@echo "  make uninstall  - Remove installed script"
	@echo "  make test       - Run syntax and smoke tests"
	@echo "  make lint       - Check scripts with shellcheck"
	@echo "  make format     - Format scripts with shfmt"
	@echo "  make clean      - Remove temporary files"
	@echo "  make version    - Show version"

install: $(SCRIPT)
	@echo "Installing $(SCRIPT) to $(INSTALL_PATH)..."
	chmod +x $(SCRIPT)
	sudo install -m 755 $(SCRIPT) $(INSTALL_PATH)
	sudo install -d $(LIB_INSTALL_DIR)/lib
	sudo install -m 644 $(LIBS) $(LIB_INSTALL_DIR)/lib/
	@echo "Installation complete. Run 'adbgath -h' to verify."

uninstall:
	@echo "Removing $(INSTALL_PATH)..."
	sudo rm -f $(INSTALL_PATH)
	sudo rm -rf $(LIB_INSTALL_DIR)
	@echo "Uninstall complete."

test: lint
	@echo "Running basic tests..."
	@bash -n $(SCRIPT)
	@for file in $(LIBS); do bash -n $$file; done
	@echo "OK Syntax check passed"
	@chmod +x $(SCRIPT)
	@./$(SCRIPT) -h > /dev/null && echo "OK Help works"
	@./$(SCRIPT) -v > /dev/null && echo "OK Version works"
	@echo "OK All tests passed"

lint:
	@echo "Linting with shellcheck..."
	@if command -v shellcheck > /dev/null; then \
		shellcheck $(SCRIPT) $(LIBS) && echo "OK No shellcheck errors"; \
	else \
		echo "WARNING shellcheck not installed. Install with: apt-get install shellcheck"; \
	fi

format:
	@echo "Formatting with shfmt..."
	@if command -v shfmt > /dev/null; then \
		shfmt -i 4 -w $(SCRIPT) $(LIBS) && echo "OK Formatted"; \
	else \
		echo "WARNING shfmt not installed. Install with: apt-get install shfmt"; \
	fi

clean:
	@echo "Cleaning up..."
	@rm -f *.log *.tmp
	@echo "OK Clean complete"

version:
	@echo "$(SCRIPT) v$(VERSION)"

.DEFAULT_GOAL := help
