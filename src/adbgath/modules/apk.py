from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.files import atomic_write_json, collision_safe_path, sha256_file
from ..errors import DependencyError, ValidationError
from ..validation import safe_local_path

PACKAGE_RE = re.compile(
    r"package:\s+name='(?P<name>[^']+)'\s+versionCode='(?P<code>[^']*)'\s+versionName='(?P<version>[^']*)'"
)
SDK_RE = re.compile(r"sdkVersion:'(?P<value>[^']+)'|targetSdkVersion:'(?P<target>[^']+)'")
COMPONENT_RE = re.compile(
    r"E:\s+(activity|activity-alias|service|receiver|provider).*?A:\s+android:name.*?=\"([^\"]+)\"", re.S
)
URL_RE = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|client[_-]?secret|access[_-]?token|private[_-]?key)\s*[:=]\s*[\"']?([A-Za-z0-9_./+=-]{12,})"
)


@dataclass(slots=True)
class ToolResult:
    ok: bool
    command: list[str]
    stdout: str
    stderr: str
    returncode: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
        }


class ApkInspector:
    def __init__(self, *, timeout: int = 120) -> None:
        self.timeout = timeout

    @staticmethod
    def _run(command: list[str], *, timeout: int = 120) -> ToolResult:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ToolResult(False, command, "", str(exc), 127)
        return ToolResult(completed.returncode == 0, command, completed.stdout, completed.stderr, completed.returncode)

    @staticmethod
    def _tools() -> dict[str, str | None]:
        return {name: shutil.which(name) for name in ["aapt2", "aapt", "apkanalyzer", "apksigner", "keytool"]}

    def inspect(self, source: str | Path, *, output: str | Path | None = None) -> dict[str, Any]:
        path = safe_local_path(source, must_exist=True)
        if path.suffix.lower() not in {".apk", ".apks", ".aab"}:
            raise ValidationError("Static analysis supports .apk, .apks, and .aab files.")
        result: dict[str, Any] = {
            "path": str(path),
            "name": path.name,
            "type": path.suffix.lower().lstrip("."),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
            "tools": self._tools(),
            "metadata": {},
            "archive": {},
            "manifest": {},
            "signing": {},
            "native_libraries": [],
            "endpoints": [],
            "potential_secrets": [],
            "findings": [],
        }
        if zipfile.is_zipfile(path):
            self._inspect_zip(path, result)
        if path.suffix.lower() == ".apk":
            self._inspect_apk_tools(path, result)
        elif path.suffix.lower() == ".apks":
            result["archive"]["apk_entries"] = [
                name for name in result["archive"].get("entries", []) if name.endswith(".apk")
            ]
        elif path.suffix.lower() == ".aab":
            result["archive"]["modules"] = sorted(
                {name.split("/", 1)[0] for name in result["archive"].get("entries", []) if "/" in name}
            )
        result["findings"] = self._findings(result)
        if output:
            target = safe_local_path(output)
            atomic_write_json(target, result)
            result["artifact"] = str(target)
        return result

    def _inspect_zip(self, path: Path, result: dict[str, Any]) -> None:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 20_000:
                raise ValidationError("Archive contains too many entries to inspect safely.")
            total_size = sum(info.file_size for info in infos)
            if total_size > 2 * 1024 * 1024 * 1024:
                raise ValidationError("Archive uncompressed size exceeds the 2 GiB inspection limit.")
            suspicious = [
                info.filename
                for info in infos
                if info.compress_size and info.file_size / max(info.compress_size, 1) > 500
            ]
            entries = [info.filename for info in infos]
            result["archive"] = {
                "entries": entries,
                "entry_count": len(entries),
                "uncompressed_size": total_size,
                "suspicious_compression_entries": suspicious[:100],
                "has_manifest": any(name.endswith("AndroidManifest.xml") for name in entries),
            }
            native = sorted(name for name in entries if re.match(r"lib/[^/]+/[^/]+\.so$", name))
            result["native_libraries"] = native
            result["native_abis"] = sorted({name.split("/")[1] for name in native})
            text_samples: list[str] = []
            manifest_text: str | None = None
            for info in infos:
                if info.file_size > 4 * 1024 * 1024:
                    continue
                lower = info.filename.lower()
                should_scan = lower.endswith(
                    (".xml", ".json", ".txt", ".js", ".html", ".properties", ".yml", ".yaml", ".conf")
                )
                should_scan = should_scan or lower.endswith(".dex")
                if not should_scan:
                    continue
                try:
                    raw = archive.read(info)
                    text = raw.decode("utf-8", errors="ignore")
                    text_samples.append(text)
                    if info.filename.endswith("AndroidManifest.xml") and text.lstrip().startswith("<"):
                        manifest_text = text
                except (KeyError, RuntimeError, OSError, MemoryError):
                    continue
            joined = "\n".join(text_samples)
            result["endpoints"] = sorted(set(URL_RE.findall(joined)))[:500]
            result["potential_secrets"] = [
                {"kind": match.group(1), "value_preview": f"{match.group(2)[:4]}…{match.group(2)[-4:]}"}
                for match in SECRET_RE.finditer(joined)
            ][:100]
            result["webview_indicators"] = sorted(
                indicator
                for indicator in {
                    "android.webkit.WebView"
                    if "android/webkit/WebView" in joined or "android.webkit.WebView" in joined
                    else "",
                    "addJavascriptInterface" if "addJavascriptInterface" in joined else "",
                    "setJavaScriptEnabled" if "setJavaScriptEnabled" in joined else "",
                    "setAllowFileAccess" if "setAllowFileAccess" in joined else "",
                }
                if indicator
            )
            if manifest_text:
                result["manifest"]["raw"] = manifest_text
                result["manifest"].update(self._parse_manifest_text(manifest_text))

    def _inspect_apk_tools(self, path: Path, result: dict[str, Any]) -> None:
        tools = result["tools"]
        badging: ToolResult | None = None
        if tools.get("aapt2"):
            badging = self._run([str(tools["aapt2"]), "dump", "badging", str(path)], timeout=self.timeout)
        elif tools.get("aapt"):
            badging = self._run([str(tools["aapt"]), "dump", "badging", str(path)], timeout=self.timeout)
        if badging and badging.ok:
            result["metadata"]["badging"] = badging.stdout
            first = PACKAGE_RE.search(badging.stdout)
            if first:
                result["metadata"].update(first.groupdict())
            for match in SDK_RE.finditer(badging.stdout):
                if match.group("value"):
                    result["metadata"]["min_sdk"] = match.group("value")
                if match.group("target"):
                    result["metadata"]["target_sdk"] = match.group("target")
            result["metadata"]["launchable_activities"] = re.findall(
                r"launchable-activity:\s+name='([^']+)'", badging.stdout
            )
            result["manifest"]["permissions"] = sorted(
                set(re.findall(r"uses-permission:\s+name='([^']+)'", badging.stdout))
            )
        manifest_result: ToolResult | None = None
        if tools.get("apkanalyzer"):
            manifest_result = self._run(
                [str(tools["apkanalyzer"]), "manifest", "print", str(path)], timeout=self.timeout
            )
        elif tools.get("aapt2"):
            manifest_result = self._run(
                [str(tools["aapt2"]), "dump", "xmltree", str(path), "AndroidManifest.xml"], timeout=self.timeout
            )
        if manifest_result and manifest_result.ok:
            manifest = manifest_result.stdout
            result["manifest"]["raw"] = manifest
            result["manifest"].update(self._parse_manifest_text(manifest))
        if tools.get("apksigner"):
            signing = self._run(
                [str(tools["apksigner"]), "verify", "--verbose", "--print-certs", str(path)], timeout=self.timeout
            )
            result["signing"] = signing.to_dict()
            if signing.ok:
                result["signing"]["schemes"] = {
                    scheme: bool(re.search(rf"Verified using v{scheme} scheme.*?: true", signing.stdout, re.I))
                    for scheme in (1, 2, 3, 4)
                }

    @staticmethod
    def _parse_manifest_text(manifest: str) -> dict[str, Any]:
        lowered = manifest.lower()
        components: list[dict[str, Any]] = []
        # Works best with apkanalyzer XML; aapt2 output remains preserved for manual review.
        for kind in ["activity", "activity-alias", "service", "receiver", "provider"]:
            pattern = re.compile(
                rf"<{kind}\b(?P<attrs>.*?)>(?P<body>.*?)</{kind}>|<{kind}\b(?P<self>.*?)/>", re.S | re.I
            )
            for match in pattern.finditer(manifest):
                attrs = match.group("attrs") or match.group("self") or ""
                name_match = re.search(r"android:name=[\"']([^\"']+)", attrs)
                exported_match = re.search(r"android:exported=[\"']([^\"']+)", attrs)
                permission_match = re.search(r"android:permission=[\"']([^\"']+)", attrs)
                body = match.group("body") or ""
                if name_match:
                    components.append(
                        {
                            "type": kind,
                            "name": name_match.group(1),
                            "exported": exported_match.group(1).lower() == "true" if exported_match else None,
                            "permission": permission_match.group(1) if permission_match else None,
                            "intent_filters": body.lower().count("<intent-filter"),
                        }
                    )
        deep_link_values = sorted(
            set(re.findall(r"android:(?:scheme|host|path|pathPrefix|pathPattern)=[\"']([^\"']+)", manifest))
        )
        deep_links: list[dict[str, str]] = []
        for attrs in re.findall(r"<data\b([^>]*)/?>", manifest, re.I):
            item: dict[str, str] = {}
            for key in ("scheme", "host", "port", "path", "pathPrefix", "pathPattern", "mimeType"):
                match = re.search(rf"android:{key}=[\"']([^\"']+)", attrs, re.I)
                if match:
                    item[key] = match.group(1)
            if item and item not in deep_links:
                deep_links.append(item)
        permission_definitions: list[dict[str, str | None]] = []
        seen_permissions: set[tuple[str, str | None]] = set()
        for attrs in re.findall(r"<permission\b([^>]*?)/?>", manifest, re.I):
            name = re.search(r"android:name=[\"']([^\"']+)", attrs, re.I)
            level = re.search(r"android:protectionLevel=[\"']([^\"']+)", attrs, re.I)
            if name:
                identity = (name.group(1), level.group(1) if level else None)
                if identity not in seen_permissions:
                    permission_definitions.append({"name": identity[0], "protection_level": identity[1]})
                    seen_permissions.add(identity)
        return {
            "components": components,
            "deep_link_values": deep_link_values,
            "deep_links": deep_links,
            "debuggable": bool(re.search(r"android:debuggable=[\"']true", manifest, re.I)),
            "allow_backup": None
            if "android:allowbackup" not in lowered
            else bool(re.search(r"android:allowBackup=[\"']true", manifest, re.I)),
            "full_backup_content": (
                re.search(r"android:fullBackupContent=[\"']([^\"']+)", manifest, re.I) or [None, None]
            )[1],
            "data_extraction_rules": (
                re.search(r"android:dataExtractionRules=[\"']([^\"']+)", manifest, re.I) or [None, None]
            )[1],
            "uses_cleartext_traffic": bool(re.search(r"android:usesCleartextTraffic=[\"']true", manifest, re.I)),
            "network_security_config": (
                re.search(r"android:networkSecurityConfig=[\"']([^\"']+)", manifest, re.I) or [None, None]
            )[1],
            "task_affinities": sorted(set(re.findall(r"android:taskAffinity=[\"']([^\"']*)", manifest, re.I))),
            "launch_modes": sorted(set(re.findall(r"android:launchMode=[\"']([^\"']+)", manifest, re.I))),
            "custom_permissions": permission_definitions,
        }

    @staticmethod
    def _findings(result: dict[str, Any]) -> list[dict[str, Any]]:
        manifest = result.get("manifest", {})
        findings: list[dict[str, Any]] = []

        def add(
            rule_id: str,
            title: str,
            severity: str,
            evidence: str,
            mitigation: str,
            *,
            component: str = "AndroidManifest.xml",
            confidence: str = "high",
        ) -> None:
            findings.append(
                {
                    "rule_id": rule_id,
                    "title": title,
                    "severity": severity,
                    "confidence": confidence,
                    "component": component,
                    "description": title,
                    "evidence": evidence,
                    "impact": "The affected configuration may expand the application attack surface or weaken a platform security control.",
                    "validation": "Confirm the behavior on an authorized test device and review component-level authorization checks.",
                    "false_positive": "The behavior may be intentional when protected by strong permissions or in-component authorization.",
                    "mitigation": mitigation,
                    "references": ["OWASP MASVS", "OWASP MASTG", "MITRE CWE"],
                }
            )

        if manifest.get("debuggable"):
            add(
                "ANDROID-APP-DEBUG-001",
                "Application is debuggable",
                "high",
                "android:debuggable=true",
                "Disable debugging in production builds.",
            )
        if manifest.get("allow_backup") is True:
            add(
                "ANDROID-APP-BACKUP-001",
                "Application backup is allowed",
                "medium",
                "android:allowBackup=true",
                "Disable legacy backup or define restrictive data extraction rules for sensitive applications.",
            )
        if manifest.get("uses_cleartext_traffic"):
            add(
                "ANDROID-APP-NET-001",
                "Cleartext traffic is permitted",
                "medium",
                "android:usesCleartextTraffic=true",
                "Disable cleartext traffic and use a restrictive Network Security Configuration.",
            )
        for component in manifest.get("components", []):
            if component.get("exported") and not component.get("permission"):
                add(
                    "ANDROID-APP-EXPORTED-001",
                    f"Exported {component['type']} is not permission-protected",
                    "high" if component["type"] in {"provider", "service"} else "medium",
                    json.dumps(component, ensure_ascii=False),
                    "Set android:exported=false when external access is unnecessary, or enforce a signature-level permission and runtime authorization.",
                    component=component.get("name", "AndroidManifest.xml"),
                )
        for permission in manifest.get("custom_permissions", []):
            level = str(permission.get("protection_level") or "normal").lower()
            if "signature" not in level:
                add(
                    "ANDROID-APP-PERMISSION-001",
                    "Custom permission does not use signature protection",
                    "medium",
                    json.dumps(permission, ensure_ascii=False),
                    "Use a signature-level custom permission for privileged cross-application operations.",
                    component=permission.get("name", "AndroidManifest.xml"),
                )
        for component in manifest.get("components", []):
            if component.get("exported") is None and component.get("intent_filters"):
                add(
                    "ANDROID-APP-EXPORTED-IMPLICIT-001",
                    f"{component['type']} has intent filters without an explicit exported value",
                    "medium",
                    json.dumps(component, ensure_ascii=False),
                    "Set android:exported explicitly and disable external access when it is not required.",
                    component=component.get("name", "AndroidManifest.xml"),
                    confidence="medium",
                )
        if manifest.get("task_affinities") and any(value not in {"", None} for value in manifest["task_affinities"]):
            add(
                "ANDROID-APP-TASK-001",
                "Custom task affinity is configured",
                "low",
                json.dumps(manifest["task_affinities"]),
                "Avoid custom task affinities for transaction-sensitive activities unless required and safely designed.",
                confidence="medium",
            )
        if "addJavascriptInterface" in result.get("webview_indicators", []):
            add(
                "ANDROID-APP-WEBVIEW-001",
                "WebView JavaScript bridge indicator detected",
                "medium",
                "addJavascriptInterface",
                "Expose only minimal bridge methods, require trusted content, and disable JavaScript when unnecessary.",
                confidence="low",
            )
        if result.get("archive", {}).get("suspicious_compression_entries"):
            add(
                "ANDROID-APP-ARCHIVE-001",
                "Suspicious archive compression ratio detected",
                "low",
                json.dumps(result["archive"]["suspicious_compression_entries"][:10]),
                "Review the archive for malformed or intentionally compressed content before processing it with other tools.",
                confidence="medium",
            )
        if result.get("potential_secrets"):
            add(
                "ANDROID-APP-SECRETS-001",
                "Potential secrets are embedded in application resources",
                "high",
                json.dumps(result["potential_secrets"][:10]),
                "Remove static secrets and retrieve short-lived credentials from a protected backend.",
                confidence="medium",
            )
        if result.get("endpoints"):
            http = [value for value in result["endpoints"] if value.lower().startswith("http://")]
            if http:
                add(
                    "ANDROID-APP-ENDPOINT-001",
                    "Plain HTTP endpoints are embedded",
                    "medium",
                    "\n".join(http[:20]),
                    "Use HTTPS endpoints and enforce transport security.",
                    confidence="medium",
                )
        return findings


class BundletoolManager:
    def __init__(self, *, jar: str | Path | None = None) -> None:
        self.jar = Path(jar).expanduser().resolve() if jar else self._discover_jar()
        self.executable = shutil.which("bundletool")
        self.java = shutil.which("java")

    @staticmethod
    def _discover_jar() -> Path | None:
        candidates = [
            Path(os.environ.get("BUNDLETOOL_JAR", "")),
            Path.home() / ".adbgath" / "tools" / "bundletool.jar",
            Path(os.environ.get("ADBGATH_HOME", Path.home() / ".adbgath")) / "tools" / "bundletool.jar",
        ]
        return next((path.expanduser().resolve() for path in candidates if str(path) and path.is_file()), None)

    def command(self, args: list[str]) -> list[str]:
        if self.executable:
            return [self.executable, *args]
        if self.java and self.jar and self.jar.is_file():
            return [self.java, "-jar", str(self.jar), *args]
        raise DependencyError("bundletool was not found. Install it or set BUNDLETOOL_JAR.")

    def run(self, args: list[str], *, timeout: int = 900) -> ToolResult:
        return ApkInspector._run(self.command(args), timeout=timeout)

    def device_spec(self, adb_serial: str, output: Path) -> ToolResult:
        return self.run(["get-device-spec", f"--device-id={adb_serial}", f"--output={output}"])

    def build_apks(self, aab: Path, output: Path, *, device_spec: Path | None = None) -> ToolResult:
        args = ["build-apks", f"--bundle={aab}", f"--output={output}", "--overwrite"]
        if device_spec:
            args.append(f"--device-spec={device_spec}")
        return self.run(args)

    def install_apks(self, archive: Path, *, adb_serial: str | None = None) -> ToolResult:
        args = ["install-apks", f"--apks={archive}"]
        if adb_serial:
            args.append(f"--device-id={adb_serial}")
        return self.run(args)

    @staticmethod
    def extract_apks(archive: Path, output: Path) -> list[str]:
        output.mkdir(parents=True, exist_ok=True)
        artifacts: list[str] = []
        with zipfile.ZipFile(archive) as zipped:
            for info in zipped.infolist():
                if not info.filename.endswith(".apk") or info.is_dir():
                    continue
                destination = collision_safe_path(output, Path(info.filename).name)
                with zipped.open(info) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                artifacts.append(str(destination))
        if not artifacts:
            raise ValidationError("The .apks archive did not contain APK entries.")
        return artifacts


def discover_apk_set(source: str | Path) -> list[Path]:
    path = safe_local_path(source, must_exist=True)
    if path.is_dir():
        files = sorted(item for item in path.rglob("*.apk") if item.is_file())
    elif path.suffix.lower() == ".apks":
        temp = Path(tempfile.mkdtemp(prefix="adbgath-apks-"))
        BundletoolManager.extract_apks(path, temp)
        files = sorted(temp.glob("*.apk"))
    elif path.suffix.lower() == ".apk":
        files = [path]
    else:
        raise ValidationError("APK set source must be an APK, APKS archive, or directory.")
    if not files:
        raise ValidationError("No APK files were found in the selected source.")
    return files


def _apk_identity(path: Path) -> dict[str, Any]:
    tools = ApkInspector._tools()
    package = None
    certificate = None
    badging_tool = tools.get("aapt2") or tools.get("aapt")
    if badging_tool:
        badging = ApkInspector._run([str(badging_tool), "dump", "badging", str(path)], timeout=120)
        if badging.ok:
            match = PACKAGE_RE.search(badging.stdout)
            package = match.group("name") if match else None
    if tools.get("apksigner"):
        signing = ApkInspector._run(
            [str(tools["apksigner"]), "verify", "--print-certs", str(path)],
            timeout=120,
        )
        if signing.ok:
            match = re.search(r"Signer #1 certificate SHA-256 digest:\s*([A-Fa-f0-9:]+)", signing.stdout)
            certificate = match.group(1).replace(":", "").lower() if match else None
    return {"path": str(path), "package": package, "certificate_sha256": certificate}


def validate_apk_set(files: Iterable[Path]) -> dict[str, Any]:
    items = list(files)
    if not items:
        raise ValidationError("At least one APK is required.")
    base = [path for path in items if path.name == "base.apk" or "base-master" in path.name]
    identities = [_apk_identity(path) for path in items]
    packages = {item["package"] for item in identities if item["package"]}
    certificates = {item["certificate_sha256"] for item in identities if item["certificate_sha256"]}
    if len(packages) > 1:
        raise ValidationError("The selected APK set contains more than one package name.")
    if len(certificates) > 1:
        raise ValidationError("The selected APK set contains incompatible signing certificates.")
    warnings = []
    if not base and len(items) > 1:
        warnings.append("No obvious base APK was found; adb may reject the set.")
    if not packages:
        warnings.append("Package consistency could not be verified because aapt/aapt2 is unavailable.")
    if not certificates:
        warnings.append("Signing consistency could not be verified because apksigner is unavailable.")
    return {
        "count": len(items),
        "files": [str(path) for path in items],
        "base_candidates": [str(path) for path in base],
        "package": next(iter(packages), None),
        "certificate_sha256": next(iter(certificates), None),
        "identities": identities,
        "warnings": warnings,
    }
