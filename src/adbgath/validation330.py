from __future__ import annotations

import ipaddress
import re

from .errors import ValidationError
from .models330 import HostPort

HOSTNAME_RE = re.compile(r"^(?=.{1,253}\.?$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?$")
PAIRING_CODE_RE = re.compile(r"^\d{6}$")
ALIAS_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,80}$")


def parse_host_port(value: str) -> HostPort:
    text = str(value or "").strip()
    if not text or any(character.isspace() for character in text):
        raise ValidationError("Expected HOST:PORT without spaces.")
    if text.startswith("["):
        closing = text.find("]")
        if closing < 2 or closing + 1 >= len(text) or text[closing + 1] != ":":
            raise ValidationError("Bracket IPv6 addresses as [ADDRESS]:PORT.")
        host, port_text = text[1:closing], text[closing + 2 :]
    else:
        if text.count(":") != 1:
            raise ValidationError("Expected HOST:PORT. Bracket IPv6 addresses as [ADDRESS]:PORT.")
        host, port_text = text.rsplit(":", 1)
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValidationError("Invalid port.") from exc
    if not 1 <= port <= 65535:
        raise ValidationError("Port must be between 1 and 65535.")
    normalized_host = host.rstrip(".")
    if not normalized_host:
        raise ValidationError("Host cannot be empty.")
    ip_candidate = normalized_host.split("%", 1)[0]
    try:
        parsed_ip = ipaddress.ip_address(ip_candidate)
        if "%" in normalized_host and parsed_ip.version != 6:
            raise ValidationError("A scope identifier is only valid for IPv6.")
    except ValueError:
        if not HOSTNAME_RE.fullmatch(normalized_host):
            raise ValidationError("Host must be an IPv4/IPv6 address or a valid DNS/.local hostname.")
    return HostPort(normalized_host, port)


def validate_host_port(value: str) -> str:
    return parse_host_port(value).endpoint


def validate_pairing_code(value: str) -> str:
    code = str(value or "").strip()
    if not PAIRING_CODE_RE.fullmatch(code):
        raise ValidationError("Pairing code must contain exactly six digits.")
    return code


def validate_alias(value: str) -> str:
    alias = str(value or "").strip()
    if not ALIAS_RE.fullmatch(alias):
        raise ValidationError("Alias must contain 1-80 printable characters.")
    return alias
