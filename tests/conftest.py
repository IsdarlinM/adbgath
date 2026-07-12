from __future__ import annotations

from pathlib import Path

import pytest

from adbgath.models import CommandResult, Device
from adbgath.service import AdbgathService


class FakeAdb:
    def __init__(self, tmp_path: Path) -> None:
        self.adb_path = tmp_path / ("adb.exe" if __import__("os").name == "nt" else "adb")
        self.adb_path.write_text("fake", encoding="utf-8")
        self.calls: list[tuple[list[str], str | None]] = []

    def build(self, args, *, serial=None):
        command = [str(self.adb_path)]
        if serial:
            command += ["-s", serial]
        return command + list(args)

    def require_device(self, serial):
        return serial or "emulator-5554"

    def devices(self):
        return [Device(serial="emulator-5554", state="device", product="sdk", model="Pixel_8")]

    def version(self):
        return CommandResult(
            ok=True, command=[str(self.adb_path), "version"], stdout="Android Debug Bridge version 1.0.41\n"
        )

    def stream(self, args, *, serial=None):
        self.calls.append((list(args), serial))
        yield "07-11 12:00:00.000  100  100 I Test: hello"
        yield "07-11 12:00:01.000  100  100 E Test: exception"

    def run(self, args, *, serial=None, timeout=None, check=True, cwd=None):
        del timeout, check, cwd
        args = list(args)
        self.calls.append((args, serial))
        stdout = ""
        if args[:4] == ["shell", "su", "-c", "id"]:
            stdout = "uid=0(root) gid=0(root)\n"
        elif args[:4] == ["shell", "pm", "list", "users"]:
            stdout = "Users:\n\tUserInfo{0:Owner:13} running\n\tUserInfo{10:Work:30}\n"
        elif args[:4] == ["shell", "am", "get-current-user"]:
            stdout = "0\n"
        elif args[:4] == ["shell", "pm", "list", "packages"]:
            if "-f" in args:
                stdout = (
                    "package:/data/app/com.example/base.apk=com.example.app\n"
                    "package:/system/app/System.apk=com.android.system\n"
                )
            else:
                stdout = "package:com.example.app\npackage:com.android.system\n"
        elif args[:3] == ["shell", "pm", "path"]:
            stdout = f"package:/data/app/{args[3]}/base.apk\n"
        elif args[:3] == ["shell", "getprop", "ro.product.manufacturer"]:
            stdout = "Google\n"
        elif args[:3] == ["shell", "getprop", "ro.product.model"]:
            stdout = "Pixel 8\n"
        elif args[:3] == ["shell", "getprop", "ro.build.version.release"]:
            stdout = "15\n"
        elif args[:3] == ["shell", "getprop", "ro.build.version.sdk"]:
            stdout = "35\n"
        elif args[:3] == ["shell", "getprop", "ro.build.version.security_patch"]:
            stdout = "2026-07-05\n"
        elif args[:3] == ["shell", "getprop", "ro.build.fingerprint"]:
            stdout = "google/test/fingerprint\n"
        elif args[:3] == ["shell", "getprop", "ro.boot.verifiedbootstate"]:
            stdout = "orange\n"
        elif args[:3] == ["shell", "getprop", "ro.debuggable"]:
            stdout = "1\n"
        elif args[:3] == ["shell", "getprop", "ro.secure"]:
            stdout = "0\n"
        elif args[:3] == ["shell", "getprop", "ro.crypto.state"]:
            stdout = "encrypted\n"
        elif args[:2] == ["shell", "getenforce"]:
            stdout = "Permissive\n"
        elif args[:5] == ["shell", "settings", "get", "global", "http_proxy"]:
            stdout = "127.0.0.1:8080\n"
        elif args[:3] == ["shell", "ip", "-brief"]:
            stdout = "wlan0 UP 192.168.1.5/24\n"
        elif args[:2] == ["shell", "ip"]:
            stdout = "default via 192.168.1.1 dev wlan0\n"
        elif args[:3] == ["shell", "getprop", "net.dns1"]:
            stdout = "8.8.8.8\n"
        elif args[:3] == ["shell", "dumpsys", "package"] and len(args) == 4:
            stdout = "android.permission.INTERNET: granted=true\nandroid.permission.CAMERA: granted=false\n"
        elif args[:3] == ["shell", "dumpsys", "window"]:
            stdout = "mCurrentFocus=Window{ com.example.app/.MainActivity }\n"
        elif args[:3] == ["shell", "ps", "-A"]:
            stdout = "USER PID NAME\nu0_a1 100 com.example.app\n"
        elif args[:3] == ["shell", "pidof", "com.example.app"]:
            stdout = "100\n"
        elif args and args[0] == "pull":
            destination = Path(args[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"APK")
            stdout = "1 file pulled\n"
        elif args and args[0] in {"install", "uninstall", "connect", "disconnect", "forward", "reverse", "logcat"}:
            stdout = "Success\n"
        return CommandResult(ok=True, command=self.build(args, serial=serial), stdout=stdout)


@pytest.fixture()
def fake_adb(tmp_path: Path) -> FakeAdb:
    return FakeAdb(tmp_path)


@pytest.fixture()
def service(fake_adb: FakeAdb, tmp_path: Path) -> AdbgathService:
    return AdbgathService(fake_adb, workspace=tmp_path / "workspace")
