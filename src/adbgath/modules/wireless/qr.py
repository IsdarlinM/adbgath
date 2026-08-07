from __future__ import annotations

import secrets
import string
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import qrcode
import qrcode.image.svg

from ...errors import AdbgathError, ValidationError

_SERVICE_ALPHABET = string.ascii_letters + string.digits
_SECRET_ALPHABET = string.ascii_letters + string.digits
_TERMINAL_STATES = frozenset({"connected", "completed", "failed", "expired", "cancelled"})


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def build_adb_qr_payload(instance: str, secret: str) -> str:
    """Build the ADB Wi-Fi QR payload documented by AOSP.

    ADB reuses the Wi-Fi QR grammar with T:ADB, S:<mDNS instance>, and
    P:<pairing secret>. Generated values deliberately use an alphanumeric
    alphabet so no QR escaping is required.
    """
    if not instance.startswith("studio-") or not (7 < len(instance) <= 63):
        raise ValidationError("QR pairing instance must start with 'studio-' and fit an mDNS label.")
    if not secret or len(secret) < 10 or len(secret) > 64 or not secret.isalnum():
        raise ValidationError("QR pairing secret must be 10-64 alphanumeric characters.")
    return f"WIFI:T:ADB;S:{instance};P:{secret};;"


def render_qr_svg(payload: str) -> bytes:
    image = qrcode.make(
        payload,
        image_factory=qrcode.image.svg.SvgPathImage,
        border=4,
        box_size=10,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    return image.to_string(encoding="utf-8")


@dataclass(slots=True)
class QrPairingSession:
    id: str
    instance: str
    secret: str
    created_at: str
    expires_at_monotonic: float
    ttl_seconds: int
    state: str = "created"
    message: str = "QR code created. Scan it from Android Wireless debugging."
    endpoint: str | None = None
    connect_endpoint: str | None = None
    pair_result: dict[str, Any] | None = None
    connect_result: dict[str, Any] | None = None
    error: str | None = None
    completed_at: str | None = None
    sequence: int = 0
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    condition: threading.Condition = field(default_factory=threading.Condition, repr=False)
    worker: threading.Thread | None = field(default=None, repr=False)
    svg: bytes = field(default=b"", repr=False)

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_STATES

    @property
    def remaining_seconds(self) -> int:
        return max(0, int(self.expires_at_monotonic - time.monotonic()))

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "instance": self.instance,
            "state": self.state,
            "message": self.message,
            "endpoint": self.endpoint,
            "connect_endpoint": self.connect_endpoint,
            "pair_result": self.pair_result,
            "connect_result": self.connect_result,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "ttl_seconds": self.ttl_seconds,
            "remaining_seconds": self.remaining_seconds,
            "sequence": self.sequence,
            "terminal": self.terminal,
            "secret_redacted": True,
        }


class QrPairingCoordinator:
    """In-memory one-time ADB QR pairing sessions.

    Secrets and raw QR payloads are never written to SQLite, metrics, jobs, or
    application logs. Sessions expire automatically and are removed from memory.
    """

    def __init__(self, wireless_manager: Any, *, workspace: Path) -> None:
        self.wireless = wireless_manager
        self.workspace = workspace
        self._sessions: dict[str, QrPairingSession] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        cutoff = time.monotonic() - 300
        with self._lock:
            stale = [
                session_id
                for session_id, session in self._sessions.items()
                if session.terminal and session.expires_at_monotonic < cutoff
            ]
            for session_id in stale:
                session = self._sessions.pop(session_id)
                session.secret = ""
                session.svg = b""

    def create(self, *, ttl_seconds: int = 120, auto_connect: bool = True, start: bool = True) -> dict[str, Any]:
        if ttl_seconds < 30 or ttl_seconds > 300:
            raise ValidationError("QR pairing TTL must be between 30 and 300 seconds.")
        self._prune()
        session_id = f"qr_{uuid.uuid4().hex[:16]}"
        instance = "studio-" + "".join(secrets.choice(_SERVICE_ALPHABET) for _ in range(10))
        secret = "".join(secrets.choice(_SECRET_ALPHABET) for _ in range(12))
        payload = build_adb_qr_payload(instance, secret)
        session = QrPairingSession(
            id=session_id,
            instance=instance,
            secret=secret,
            created_at=_utc_now(),
            expires_at_monotonic=time.monotonic() + ttl_seconds,
            ttl_seconds=ttl_seconds,
            svg=render_qr_svg(payload),
        )
        with self._lock:
            self._sessions[session_id] = session
        if start:
            worker = threading.Thread(
                target=self._run,
                args=(session, auto_connect),
                name=f"adbgath-qr-{session_id[-6:]}",
                daemon=True,
            )
            session.worker = worker
            worker.start()
        return session.public()

    def _update(self, session: QrPairingSession, state: str, message: str, **values: Any) -> None:
        with session.condition:
            session.state = state
            session.message = message
            for key, value in values.items():
                setattr(session, key, value)
            session.sequence += 1
            if state in _TERMINAL_STATES:
                session.completed_at = _utc_now()
            session.condition.notify_all()

    def _matching_pairing_service(self, session: QrPairingSession) -> dict[str, Any] | None:
        discovery = self.wireless.discover(refresh=True, detailed=True)
        for service in discovery.get("pairing_services", []):
            if service.get("instance") == session.instance:
                return service
        return None

    @staticmethod
    def _connection_candidates(discovery: dict[str, Any], pairing_service: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = list(discovery.get("connect_services", []))
        serial = pairing_service.get("serial")
        host = pairing_service.get("host")
        if serial:
            exact = [item for item in candidates if item.get("serial") == serial]
            if exact:
                return exact
        same_host = [item for item in candidates if item.get("host") == host]
        return same_host or candidates

    def _run(self, session: QrPairingSession, auto_connect: bool) -> None:
        self._update(session, "waiting-for-scan", "Waiting for Android to scan the QR code and advertise pairing.")
        try:
            pairing_service: dict[str, Any] | None = None
            while time.monotonic() < session.expires_at_monotonic:
                if session.cancel_event.is_set():
                    self._update(session, "cancelled", "QR pairing cancelled by the operator.")
                    return
                pairing_service = self._matching_pairing_service(session)
                if pairing_service:
                    break
                session.cancel_event.wait(1.0)
            if not pairing_service:
                self._update(session, "expired", "QR pairing expired before the device advertised the matching service.")
                return

            endpoint = str(pairing_service["endpoint"])
            self._update(
                session,
                "service-discovered",
                "Matching QR pairing service discovered.",
                endpoint=endpoint,
            )
            self._update(session, "pairing", "Pairing with the discovered Android service.")
            pair_result = self.wireless.pair_secret(endpoint, session.secret, method="qr")
            public_pair = pair_result.to_dict()
            public_pair.get("metadata", {}).pop("pairing_secret", None)
            if not pair_result.ok:
                self._update(
                    session,
                    "failed",
                    "ADB rejected the QR pairing attempt.",
                    pair_result=public_pair,
                    error=pair_result.stderr.strip() or pair_result.stdout.strip() or "Pairing failed",
                )
                return
            self._update(session, "paired", "QR pairing succeeded.", pair_result=public_pair)
            if not auto_connect:
                self._update(
                    session,
                    "completed",
                    "Device paired successfully. Automatic connection was disabled.",
                    pair_result=public_pair,
                )
                return

            self._update(session, "connecting", "Pairing succeeded; locating the separate TLS connection service.")
            deadline = min(session.expires_at_monotonic, time.monotonic() + 20)
            connect_result = None
            connect_endpoint = None
            while time.monotonic() < deadline and not session.cancel_event.is_set():
                discovery = self.wireless.discover(refresh=True, detailed=True)
                candidates = self._connection_candidates(discovery, pairing_service)
                for candidate in candidates:
                    connect_endpoint = str(candidate["endpoint"])
                    connect_result = self.wireless.connect(connect_endpoint)
                    if connect_result.ok:
                        break
                if connect_result and connect_result.ok:
                    break
                session.cancel_event.wait(1.0)

            if session.cancel_event.is_set():
                self._update(session, "cancelled", "QR pairing cancelled after pairing completed.")
                return
            if connect_result and connect_result.ok:
                self._update(
                    session,
                    "connected",
                    "Device paired and connected over encrypted ADB Wi-Fi.",
                    connect_endpoint=connect_endpoint,
                    connect_result=connect_result.to_dict(),
                )
            else:
                self._update(
                    session,
                    "completed",
                    "Device paired. A connection service was not available yet; ADB may reconnect automatically.",
                    connect_endpoint=connect_endpoint,
                    connect_result=connect_result.to_dict() if connect_result else None,
                )
        except Exception as exc:  # session boundary; never expose secrets
            message = str(exc).replace(session.secret, "<redacted>")
            self._update(session, "failed", "QR pairing failed.", error=f"{type(exc).__name__}: {message}")
        finally:
            session.secret = ""

    def get(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown or expired QR pairing session: {session_id}")
        return session.public()

    def svg(self, session_id: str) -> bytes:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown or expired QR pairing session: {session_id}")
        if not session.svg:
            raise AdbgathError("QR image is no longer available for this session.")
        return session.svg

    def cancel(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown or expired QR pairing session: {session_id}")
        session.cancel_event.set()
        if not session.terminal:
            self._update(session, "cancelled", "QR pairing cancelled by the operator.")
        session.secret = ""
        return session.public()

    def wait(self, session_id: str, *, after_sequence: int = -1, timeout: float = 30.0) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown or expired QR pairing session: {session_id}")
        with session.condition:
            if session.sequence <= after_sequence and not session.terminal:
                session.condition.wait(timeout=max(0.0, min(timeout, 60.0)))
            return session.public()

    def write_svg(self, session_id: str, output: str | Path | None = None) -> Path:
        target = Path(output or self.workspace / "qr" / f"adb-pair-{session_id}.svg").expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.svg(session_id))
        return target
