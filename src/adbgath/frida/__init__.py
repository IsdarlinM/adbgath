"""Versioned, observation-only Frida helpers bundled with ADB-Gath."""

from __future__ import annotations

from typing import Any

SCRIPT_CATALOG: dict[str, dict[str, Any]] = {
    "tls-observer": {
        "version": "1.0.0",
        "description": "Observe TLS socket creation and handshake activity without bypassing validation.",
        "parameters": {},
        "safety": "observation-only",
    },
    "crypto-monitor": {
        "version": "1.0.0",
        "description": "Observe cryptographic algorithm selection without collecting keys or plaintext.",
        "parameters": {},
        "safety": "observation-only",
    },
    "webview-observer": {
        "version": "1.0.0",
        "description": "Observe WebView URL loading and JavaScript settings without modifying behavior.",
        "parameters": {},
        "safety": "observation-only",
    },
}
