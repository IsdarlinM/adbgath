from __future__ import annotations

import pytest

from adbgath.errors import ValidationError


def test_wireless_tcp_port_is_validated_before_backend(service):
    with pytest.raises(ValidationError, match="Wireless TCP port"):
        service.wireless_tcpip("emulator-5554", "not-a-port")
    with pytest.raises(ValidationError, match="at most 65535"):
        service.wireless_tcpip("emulator-5554", 70000)


def test_wireless_watch_numbers_are_validated(service):
    with pytest.raises(ValidationError, match="Wireless watch interval"):
        service.wireless_watch(interval="bad", duration=10)
    with pytest.raises(ValidationError, match="Wireless watch duration"):
        service.wireless_watch(interval=3, duration="bad")


def test_metrics_limit_is_validated(service):
    with pytest.raises(ValidationError, match="Metrics limit"):
        service.metrics("list", limit="bad")
