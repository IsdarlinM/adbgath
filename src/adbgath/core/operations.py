from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

FieldType = Literal["text", "number", "boolean", "select", "file", "textarea", "list"]


@dataclass(frozen=True, slots=True)
class OperationField:
    name: str
    label: str
    field_type: FieldType = "text"
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    placeholder: str = ""
    help: str = ""
    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True, slots=True)
class Operation:
    name: str
    title: str
    description: str
    category: str
    fields: tuple[OperationField, ...] = ()
    destructive: bool = False
    long_running: bool = False
    requirements: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ("windows", "linux")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fields"] = [asdict(item) for item in self.fields]
        return data


def f(name: str, label: str, field_type: FieldType = "text", **kwargs: Any) -> OperationField:
    return OperationField(name=name, label=label, field_type=field_type, **kwargs)


OPERATIONS: dict[str, Operation] = {
    item.name: item
    for item in [
        Operation("devices", "Devices", "List connected ADB targets.", "Device"),
        Operation("capabilities", "Device capabilities", "Detect supported Android and host capabilities.", "Device"),
        Operation(
            "connect",
            "Connect",
            "Connect to an ADB TCP endpoint.",
            "Device",
            (f("target", "Host:port", required=True),),
        ),
        Operation(
            "disconnect",
            "Disconnect",
            "Disconnect an ADB TCP endpoint.",
            "Device",
            (f("target", "Host:port", required=True),),
        ),
        Operation("users", "Android profiles", "List Android users and work profiles.", "Inventory"),
        Operation(
            "packages",
            "Packages",
            "List installed applications.",
            "Inventory",
            (
                f("include_paths", "Include paths", "boolean"),
                f("system", "Package type", "select", choices=("all", "system", "third-party"), default="all"),
            ),
        ),
        Operation("paths", "APK paths", "Resolve APK and split paths.", "APK", (f("package", "Package name"),)),
        Operation(
            "download",
            "Pull APK set",
            "Download base and split APKs.",
            "APK",
            (
                f("packages", "Packages", "list"),
                f("remote_paths", "Remote paths", "list"),
                f("output", "Output directory"),
            ),
            long_running=True,
        ),
        Operation(
            "install",
            "Install APK/APK set",
            "Install one or more compatible APK files.",
            "APK",
            (
                f("files", "APK files", "list", required=True),
                f("replace_existing", "Replace existing", "boolean"),
                f("grant_runtime_permissions", "Grant runtime permissions", "boolean"),
            ),
            destructive=True,
            long_running=True,
        ),
        Operation(
            "install_set",
            "Install split set",
            "Validate and install a split APK directory or .apks archive.",
            "APK",
            (f("source", "Directory or .apks file", required=True),),
            destructive=True,
            long_running=True,
        ),
        Operation(
            "uninstall",
            "Uninstall",
            "Uninstall packages from the selected profile.",
            "APK",
            (f("packages", "Packages", "list", required=True), f("keep_data", "Keep data", "boolean")),
            destructive=True,
        ),
        Operation(
            "replace",
            "Transactional replace",
            "Replace an app with backup and rollback.",
            "APK",
            (
                f("package", "Package", required=True),
                f("file", "APK file", "file", required=True),
                f("allow_uninstall", "Allow uninstall fallback", "boolean"),
            ),
            destructive=True,
            long_running=True,
        ),
        Operation(
            "bundle",
            "Bundletool",
            "Inspect/build/install Android App Bundles.",
            "APK",
            (
                f(
                    "mode",
                    "Mode",
                    "select",
                    required=True,
                    choices=("inspect", "device-spec", "build-apks", "install-apks", "extract"),
                ),
                f("file", "AAB/APKS file"),
                f("output", "Output"),
            ),
            destructive=True,
            long_running=True,
            requirements=("bundletool",),
        ),
        Operation(
            "info",
            "Device information",
            "Collect Android device information.",
            "Device",
            (f("mode", "Mode", "select", choices=("basic", "system", "network", "security", "all"), default="basic"),),
        ),
        Operation(
            "app",
            "Application summary",
            "Inspect an installed application.",
            "Runtime",
            (f("package", "Package", required=True),),
        ),
        Operation(
            "runtime",
            "Runtime inspection",
            "Inspect processes, activities, and services.",
            "Runtime",
            (
                f(
                    "mode",
                    "Mode",
                    "select",
                    choices=("summary", "processes", "activities", "services"),
                    default="summary",
                ),
                f("package", "Package"),
            ),
        ),
        Operation(
            "logs_capture",
            "Capture logcat",
            "Capture filtered Android logs.",
            "Evidence",
            (
                f("duration", "Duration", "number", default=30),
                f("package", "Package"),
                f("regex", "Regex"),
                f("output", "Output file"),
            ),
            long_running=True,
        ),
        Operation("logs_clear", "Clear logcat", "Clear device log buffers.", "Evidence", destructive=True),
        Operation(
            "evidence",
            "Capture evidence",
            "Collect screenshots, bugreport, dumpsys, logs, hashes, and a manifest.",
            "Evidence",
            (
                f("package", "Package"),
                f("output", "Output directory"),
                f("screen_record_seconds", "Screen record seconds", "number", default=0),
                f("redact", "Create redacted text copies", "boolean", default=True),
            ),
            long_running=True,
        ),
        Operation("sniff_interfaces", "Network interfaces", "List interfaces available for capture.", "Network"),
        Operation(
            "sniff_capture",
            "Packet capture",
            "Capture traffic on a rooted authorized device.",
            "Network",
            (
                f("interface", "Interface", default="wlan0"),
                f("duration", "Duration", "number", default=30),
                f("output", "Output file"),
            ),
            long_running=True,
            requirements=("root", "tcpdump"),
        ),
        Operation(
            "push_tcpdump",
            "Push tcpdump",
            "Push a researcher-supplied tcpdump binary.",
            "Network",
            (f("file", "Binary", "file", required=True),),
            destructive=True,
            requirements=("root",),
        ),
        Operation(
            "proxy",
            "HTTP proxy",
            "Show, set, or clear the global device proxy.",
            "Network",
            (f("mode", "Mode", "select", choices=("show", "set", "clear"), default="show"), f("spec", "Host:port")),
            destructive=True,
        ),
        Operation(
            "forward",
            "Port mapping",
            "Create ADB forward or reverse mappings.",
            "Network",
            (
                f("mode", "Mode", "select", choices=("forward", "reverse"), default="forward"),
                f("local_port", "Local port", "number", default=8080),
                f("remote_port", "Remote port", "number", default=8080),
            ),
            destructive=True,
        ),
        Operation(
            "backup",
            "Application backup",
            "Collect app-private files using run-as when authorized and supported.",
            "Evidence",
            (f("package", "Package", required=True), f("output", "Output file")),
            long_running=True,
        ),
        Operation(
            "content",
            "Content providers",
            "Enumerate content provider metadata.",
            "Runtime",
            (f("package", "Package"),),
        ),
        Operation(
            "frida",
            "Frida",
            "Run controlled Frida workflows and versioned scripts.",
            "Dynamic analysis",
            (
                f("mode", "Mode", "select", choices=("ps", "attach", "spawn", "scripts", "history"), default="ps"),
                f("package", "Package"),
                f("script", "Script file"),
                f("limit", "History limit", "number", default=100, minimum=1, maximum=1000),
                f("redact", "Redact stored logs", "boolean", default=True),
            ),
            long_running=True,
            requirements=("frida",),
        ),
        Operation(
            "static",
            "Static APK analysis",
            "Analyze manifest, signing, libraries, endpoints, and security configuration.",
            "Static analysis",
            (f("file", "APK/APKS/AAB file", "file", required=True), f("output", "Output file")),
            long_running=True,
        ),
        Operation(
            "assess",
            "Application assessment",
            "Run a reproducible static and device-side assessment workflow.",
            "Assessment",
            (
                f("package", "Package", required=True),
                f("apk", "Optional local APK"),
                f("project_id", "Project ID"),
                f("output", "Output directory"),
            ),
            long_running=True,
        ),
        Operation(
            "security",
            "Device posture audit",
            "Run defensive posture rules and produce reports.",
            "Assessment",
            (f("output", "Output file"),),
            long_running=True,
        ),
        Operation(
            "collect",
            "Collection",
            "Collect package, runtime, and device evidence.",
            "Evidence",
            (f("output", "Output directory"),),
            long_running=True,
        ),
        Operation(
            "mastg",
            "MASTG collection",
            "Create an OWASP MASTG-oriented evidence bundle.",
            "Evidence",
            (f("output", "Output directory"),),
            long_running=True,
        ),
        Operation(
            "inventory",
            "Inventory",
            "Export a device and package inventory.",
            "Inventory",
            (f("output", "Output file"),),
        ),
        Operation(
            "snapshot_create",
            "Create snapshot",
            "Capture a comparable device/application state.",
            "Snapshots",
            (f("name", "Snapshot name", required=True), f("package", "Package"), f("project_id", "Project ID")),
        ),
        Operation(
            "snapshot_diff",
            "Compare snapshots",
            "Compare two saved states.",
            "Snapshots",
            (
                f("before", "Before snapshot", required=True),
                f("after", "After snapshot", required=True),
                f("output", "Output file"),
            ),
        ),
        Operation(
            "projects",
            "Projects",
            "List, create, inspect, or export persistent assessment projects.",
            "Workspace",
            (
                f("mode", "Mode", "select", choices=("list", "create", "sessions", "export"), default="list"),
                f("project_id", "Project ID"),
                f("name", "Name"),
                f("description", "Description", "textarea"),
                f("scope", "Scope", "textarea"),
                f("output", "Export ZIP path"),
            ),
        ),
        Operation(
            "findings",
            "Findings",
            "List findings or update their workflow state.",
            "Workspace",
            (
                f("project_id", "Project ID"),
                f("finding_id", "Finding ID"),
                f("status", "Status", "select", choices=("open", "validated", "false-positive", "accepted", "fixed")),
            ),
        ),
        Operation(
            "groups",
            "Device groups",
            "Create and manage multi-device target groups.",
            "Device",
            (
                f("mode", "Mode", "select", choices=("list", "add", "remove"), default="list"),
                f("name", "Group"),
                f("serial", "Serial"),
            ),
        ),
        Operation(
            "run_group",
            "Run on group",
            "Execute a safe read-only operation concurrently across a device group.",
            "Device",
            (
                f("group", "Group", required=True),
                f(
                    "operation",
                    "Operation",
                    "select",
                    choices=("inventory", "info", "security", "capabilities"),
                    required=True,
                ),
            ),
            long_running=True,
        ),
        Operation(
            "reports",
            "Export report",
            "Export saved findings as HTML, Markdown, JSON, CSV, SARIF, or PDF.",
            "Reports",
            (
                f("project_id", "Project ID", required=True),
                f("format", "Format", "select", choices=("html", "md", "json", "csv", "sarif", "pdf"), default="html"),
                f("output", "Output file"),
            ),
        ),
        Operation(
            "plugins",
            "Plugins",
            "List or explicitly run installed ADB-Gath plugins.",
            "System",
            (
                f("mode", "Mode", "select", choices=("list", "run"), default="list"),
                f("name", "Plugin name"),
                f("package", "Package"),
                f("allow_permissions", "Allowed plugin permissions", "list"),
            ),
            destructive=True,
            long_running=True,
        ),
        Operation(
            "doctor",
            "Doctor",
            "Validate Python, ADB, optional tools, drivers, and workspace.",
            "System",
            (f("fix", "Apply safe repairs", "boolean"),),
        ),
        Operation(
            "update",
            "Secure update",
            "Check, plan, install, or roll back a signed/checksummed release.",
            "System",
            (
                f("mode", "Mode", "select", choices=("check", "plan", "install", "rollback"), default="check"),
                f("archive", "Local verified archive"),
                f("checksum", "SHA-256"),
            ),
            destructive=True,
            long_running=True,
        ),
    ]
}

WEB_ACTIONS = frozenset(OPERATIONS)


def operation_catalog() -> list[dict[str, Any]]:
    return [item.to_dict() for item in sorted(OPERATIONS.values(), key=lambda op: (op.category, op.title))]


def validate_operation_payload(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a web/job payload against the shared operation catalog."""
    if action not in OPERATIONS:
        raise ValueError(f"Unsupported action: {action}")
    operation = OPERATIONS[action]
    allowed = {field.name for field in operation.fields} | {"device", "user"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"Unsupported fields for {action}: {', '.join(unknown)}")
    normalized: dict[str, Any] = {}
    for field in operation.fields:
        value = payload.get(field.name, field.default)
        if field.required and (value is None or value == "" or value == []):
            raise ValueError(f"{field.label} is required")
        if value is None:
            continue
        if field.field_type == "number":
            if isinstance(value, bool):
                raise ValueError(f"{field.label} must be a number")
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field.label} must be a number") from exc
            if field.minimum is not None and value < field.minimum:
                raise ValueError(f"{field.label} must be at least {field.minimum}")
            if field.maximum is not None and value > field.maximum:
                raise ValueError(f"{field.label} must be at most {field.maximum}")
        elif field.field_type == "boolean":
            if not isinstance(value, bool):
                if str(value).lower() not in {"true", "false", "1", "0"}:
                    raise ValueError(f"{field.label} must be true or false")
                value = str(value).lower() in {"true", "1"}
        elif field.field_type == "list":
            if isinstance(value, str):
                value = [
                    item.strip() for item in value.replace("\r", "\n").replace(",", "\n").split("\n") if item.strip()
                ]
            elif not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{field.label} must be a list of strings")
        elif not isinstance(value, str):
            raise ValueError(f"{field.label} must be text")
        if field.choices and value not in field.choices:
            raise ValueError(f"{field.label} must be one of: {', '.join(field.choices)}")
        normalized[field.name] = value
    for name in ("device", "user"):
        value = payload.get(name)
        if value not in (None, ""):
            if not isinstance(value, str):
                raise ValueError(f"{name} must be text")
            normalized[name] = value
    return normalized
