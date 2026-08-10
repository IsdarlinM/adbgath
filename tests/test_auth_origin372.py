from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adbgath.authorigin370 import _origin, patch_webapp


def _app():
    app = FastAPI()

    @app.post("/auth/login")
    async def login():
        return {"ok": True}

    @app.post("/auth/setup")
    async def setup():
        return {"ok": True}

    module = SimpleNamespace(create_app=lambda **kwargs: app)
    patch_webapp(module)
    return module.create_app()


def test_origin_normalization_handles_default_ports_dns_and_ipv6():
    assert _origin("https://Example.COM") == ("https", "example.com", 443)
    assert _origin("https://example.com:443/path?q=1") == ("https", "example.com", 443)
    assert _origin("http://example.com") == ("http", "example.com", 80)
    assert _origin("https://[2001:0db8:0:0:0:0:0:1]:50001") == ("https", "2001:db8::1", 50001)
    assert _origin("ftp://example.com") is None
    assert _origin("https://user:pass@example.com") is None
    assert _origin("https://example.com:not-a-port") is None


def test_same_origin_https_login_is_allowed():
    client = TestClient(_app(), base_url="https://device.example:50001")
    response = client.post(
        "/auth/login",
        headers={"origin": "https://DEVICE.EXAMPLE:50001"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_default_https_port_is_canonicalized():
    client = TestClient(_app(), base_url="https://device.example")
    response = client.post(
        "/auth/login",
        headers={"origin": "https://device.example:443"},
    )
    assert response.status_code == 200


def test_same_origin_referer_with_path_is_allowed():
    client = TestClient(_app(), base_url="https://device.example:50001")
    response = client.post(
        "/auth/setup",
        headers={"referer": "https://device.example:50001/setup?step=1"},
    )
    assert response.status_code == 200


def test_fetch_metadata_same_origin_avoids_false_positive_origin_string():
    client = TestClient(_app(), base_url="https://device.example:50001")
    response = client.post(
        "/auth/login",
        headers={
            "origin": "null",
            "sec-fetch-site": "same-origin",
        },
    )
    assert response.status_code == 200


def test_cross_site_fetch_metadata_is_rejected_even_if_origin_looks_local():
    client = TestClient(_app(), base_url="https://device.example:50001")
    response = client.post(
        "/auth/login",
        headers={
            "origin": "https://device.example:50001",
            "sec-fetch-site": "cross-site",
        },
    )
    assert response.status_code == 403
    assert response.json() == {
        "ok": False,
        "error": "Cross-origin authentication request rejected.",
    }


def test_mismatched_origin_is_rejected_without_fetch_metadata():
    client = TestClient(_app(), base_url="https://device.example:50001")
    response = client.post(
        "/auth/login",
        headers={"origin": "https://attacker.example"},
    )
    assert response.status_code == 403


def test_http_and_https_are_not_treated_as_same_origin():
    client = TestClient(_app(), base_url="http://device.example:50001")
    response = client.post(
        "/auth/login",
        headers={"origin": "https://device.example:50001"},
    )
    assert response.status_code == 403
