from __future__ import annotations

import hashlib
from pathlib import Path

from adbgath.branding import BANNER_ART, WEB_BRAND_NAME, WEB_BRAND_TAGLINE

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_owner_approved_branding_snapshot():
    assert (
        hashlib.sha256(BANNER_ART.encode("utf-8")).hexdigest()
        == "4cae97f59955f7140b1cdfb4851ab7b4bf0549f95c2dda19405cf556a6550648"
    )
    assert WEB_BRAND_NAME == "ADB-Gath"
    assert WEB_BRAND_TAGLINE == "Defensive ADB Toolkit"


def test_web_uses_owner_branding_without_invented_wordmark():
    html = (PROJECT_ROOT / "src/adbgath/web/static/index.html").read_text(encoding="utf-8")
    assert BANNER_ART.splitlines()[0].rstrip() in html
    assert "ADB-Gath" in html
    assert "Defensive ADB Toolkit" in html
    assert "ADB<span>GATH" not in html
