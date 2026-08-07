from __future__ import annotations

from typing import Any

from ...errors import AdbgathError
from ...validation import parse_host_port, validate_pairing_code


def patch_wireless_manager(module: Any) -> None:
    cls = module.WirelessManager
    if getattr(cls, "_adbgath_340_patched", False):
        return

    def pair_secret(self, target: str, pairing_secret: str, *, method: str = "code"):
        parsed = parse_host_port(target)
        endpoint = parsed.endpoint
        if method == "code":
            secret = validate_pairing_code(pairing_secret)
        elif method == "qr":
            secret = str(pairing_secret)
            if not 10 <= len(secret) <= 64 or not secret.isalnum():
                raise AdbgathError("Invalid in-memory QR pairing secret.")
        else:
            raise AdbgathError(f"Unsupported pairing method: {method}")
        result = self.adb.run_interactive(["pair", endpoint], input_data=secret, timeout=45, check=False)
        result.metadata.update(
            {
                "endpoint": endpoint,
                "pairing_method": method,
                "pairing_secret_redacted": True,
                "pairing_code_redacted": method == "code",
            }
        )
        context = self._context_for_endpoint(endpoint)
        self.store.upsert_wireless_device(
            {
                **context,
                "instance": context.get("instance") or endpoint,
                "host": parsed.host,
                "pairing_port": parsed.port,
                "state": "paired" if result.ok else "pairing-failed",
                "metadata": {
                    "pairing_method": method,
                    "last_pair_result": result.stdout.strip() or result.stderr.strip(),
                },
            }
        )
        return result

    original_pair = cls.pair

    def pair(self, target: str, pairing_code: str):
        return pair_secret(self, target, pairing_code, method="code")

    cls.pair_secret = pair_secret
    cls.pair = pair
    cls._adbgath_340_original_pair = original_pair
    cls._adbgath_340_patched = True
