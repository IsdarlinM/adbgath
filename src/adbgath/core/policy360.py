from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any


ROLE_ORDER = ("viewer", "analyst", "operator", "administrator")

DEFAULT_RULES: dict[str, tuple[str, ...]] = {
    "viewer": (
        "devices", "capabilities", "info", "packages", "paths", "runtime", "security",
        "wireless_status", "wireless_discover", "wireless_known", "schema_status", "metrics",
        "findings", "project", "report", "snapshot", "inventory", "artifact_list", "artifact_verify",
        "lab_status", "lab_agents", "lab_pools", "lab_jobs", "audit_list", "policy_show", "sbom_generate",
    ),
    "analyst": (
        "static", "content", "logs", "logs_capture", "collect", "mastg", "assess", "evidence",
        "download", "pull", "sniff", "frida", "artifact_import", "artifact_migrate", "correlate",
    ),
    "operator": (
        "connect", "disconnect", "wireless_*", "install", "install_set", "uninstall", "replace",
        "bundle", "proxy", "forward", "backup", "run_group", "group", "lab_job_submit",
        "lab_job_cancel", "lab_pool_manage", "agent_manage", "artifact_gc", "plugin_verify",
    ),
    "administrator": ("*",),
}

DESTRUCTIVE_PATTERNS = (
    "install", "install_set", "uninstall", "replace", "bundle", "wireless_pair", "wireless_qr_create",
    "wireless_tcpip", "proxy", "forward", "lab_job_submit", "lab_job_cancel", "artifact_gc", "update",
)

REMOTE_DENY = frozenset({
    "web", "update", "plugin", "plugin_install", "controller", "agent", "lab_controller",
    "lab_agent_run", "policy_set", "policy_delete", "audit_clear",
})


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    role: str
    action: str
    reason: str
    destructive: bool
    requires_approval: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "role": self.role,
            "action": self.action,
            "reason": self.reason,
            "destructive": self.destructive,
            "requires_approval": self.requires_approval,
        }


def is_destructive(action: str) -> bool:
    return any(fnmatchcase(action, pattern) for pattern in DESTRUCTIVE_PATTERNS)


class PolicyEngine:
    def __init__(self, store: Any) -> None:
        self.store = store

    def effective_patterns(self, role: str) -> list[str]:
        if role not in ROLE_ORDER:
            return []
        patterns: list[str] = []
        index = ROLE_ORDER.index(role)
        for inherited in ROLE_ORDER[: index + 1]:
            patterns.extend(DEFAULT_RULES.get(inherited, ()))
        overrides = self.store.list_policy_rules(role=role)
        for item in overrides:
            if item["effect"] == "allow":
                patterns.append(item["action"])
        return patterns

    def decide(self, role: str, action: str, *, remote: bool = False, approved: bool = False) -> PolicyDecision:
        role = str(role or "viewer").lower()
        action = str(action or "").strip()
        destructive = is_destructive(action)
        if role not in ROLE_ORDER:
            return PolicyDecision(False, role, action, "unknown role", destructive, destructive)
        if remote and action in REMOTE_DENY:
            return PolicyDecision(False, role, action, "operation is not remotely dispatchable", destructive, destructive)

        overrides = self.store.list_policy_rules(role=role, action=action)
        for item in overrides:
            if item["effect"] == "deny":
                return PolicyDecision(False, role, action, "explicit deny policy", destructive, destructive)
            if item["effect"] == "allow":
                if destructive and not approved:
                    return PolicyDecision(False, role, action, "destructive operation requires explicit approval", True, True)
                return PolicyDecision(True, role, action, "explicit allow policy", destructive, destructive)

        allowed = any(fnmatchcase(action, pattern) for pattern in self.effective_patterns(role))
        if not allowed:
            return PolicyDecision(False, role, action, "role does not grant this operation", destructive, destructive)
        if destructive and not approved:
            return PolicyDecision(False, role, action, "destructive operation requires explicit approval", True, True)
        return PolicyDecision(True, role, action, "role policy permits operation", destructive, destructive)
