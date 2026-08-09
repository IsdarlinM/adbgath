from __future__ import annotations

import os
import socket
import threading
import time

import pytest

if os.environ.get("ADBGATH_BROWSER_E2E") != "1":
    pytest.skip("Set ADBGATH_BROWSER_E2E=1 after installing Chromium with Playwright.", allow_module_level=True)

import uvicorn
from playwright.sync_api import sync_playwright

from adbgath.webapp import create_app


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_authenticated_dashboard_renders_final_372_parity_controls(service):
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(service=service),
            host="127.0.0.1",
            port=port,
            log_level="error",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started

    page_errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")

            # First-run Web authentication must work in a real browser before
            # any dashboard capability can be considered usable.
            page.locator("input[name='username']").fill("browser-admin")
            page.locator("input[name='password']").fill("Browser-Admin-Password-372!")
            page.locator("input[name='confirm_password']").fill("Browser-Admin-Password-372!")
            page.get_by_role("button", name="Initialize secure workspace").click()
            page.wait_for_selector("#actionSelect")
            page.wait_for_function("document.querySelector('#actionSelect').options.length > 5")

            assert page.locator("#versionValue").inner_text().strip() == "3.7.2"
            assert page.locator("#auth370WorkspaceSelect").is_visible()
            assert page.locator("#ux372JobStatus").count() == 1
            assert page.locator("#ux372JobSearch").count() == 1
            assert page.locator("#ux372ArtifactSearch").count() == 1

            page.select_option("#actionSelect", "update")
            update_mode = page.locator("#dynamicFields [name='mode']")
            assert update_mode.input_value() == "auto"
            assert {option.get_attribute("value") for option in update_mode.locator("option").all()} >= {
                "auto",
                "force",
                "check",
                "plan",
                "install",
                "rollback",
            }

            page.select_option("#actionSelect", "install_set")
            assert page.locator("#dynamicFields [name='source']").count() == 1
            assert page.locator("#dynamicFields [name='replace_existing']").is_checked()
            assert page.locator("#dynamicFields [name='grant_runtime_permissions']").count() == 1

            page.select_option("#actionSelect", "logs_capture")
            for field in ("duration", "package", "pid", "regex", "filters", "output", "clear", "format"):
                assert page.locator(f"#dynamicFields [name='{field}']").count() == 1

            page.select_option("#actionSelect", "inventory_watch")
            assert page.locator("#dynamicFields [name='interval']").input_value() == "10"
            assert page.locator("#dynamicFields [name='duration']").input_value() == "60"

            # Exercise the workspace dialog in the same real-browser session.
            page.locator("#auth370WorkspaceAdd").click()
            page.locator("#auth370WorkspaceName").fill("Browser parity workspace")
            page.locator("#auth370WorkspaceCreate").click()
            page.wait_for_function(
                "[...document.querySelectorAll('#auth370WorkspaceSelect option')].some(o => o.textContent.includes('Browser parity workspace'))"
            )

            assert page_errors == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
