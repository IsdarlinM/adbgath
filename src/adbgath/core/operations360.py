from __future__ import annotations

from typing import Any


def patch_operations(module: Any) -> None:
    if "lab_status" in module.OPERATIONS:
        return
    Operation, f = module.Operation, module.f
    additions = [
        Operation(
            "artifact_store", "Content-addressed artifacts",
            "Import, list, verify, materialize, migrate, or garbage-collect deduplicated evidence objects.",
            "Evidence",
            (
                f("mode", "Mode", "select", choices=("status", "import", "list", "verify", "materialize", "migrate", "gc"), default="status"),
                f("path", "File or legacy directory"),
                f("digest", "SHA-256 digest"),
                f("output", "Materialize output"),
                f("project_id", "Project ID"),
                f("compress", "Compress text artifacts", "boolean", default=True),
                f("dry_run", "Dry run", "boolean", default=True),
            ),
        ),
        Operation(
            "correlate", "Static/runtime correlation",
            "Correlate application metadata, runtime state and optional APK static evidence into one provenance-aware result.",
            "Security",
            (f("package", "Package", required=True), f("apk", "Optional local APK", "file")),
        ),
        Operation(
            "policy", "RBAC policy",
            "Inspect or modify ADB-Gath role policy. Policy changes require administrator authorization.",
            "Lab",
            (
                f("mode", "Mode", "select", choices=("show", "check", "set", "delete"), default="show"),
                f("role", "Role", "select", choices=("viewer", "analyst", "operator", "administrator"), default="viewer"),
                f("action", "Operation"), f("effect", "Effect", "select", choices=("allow", "deny"), default="allow"),
                f("approved", "Approved", "boolean", default=False),
            ),
            destructive=True,
        ),
        Operation(
            "audit", "Audit trail",
            "List or verify the append-only hash-chained audit trail.",
            "Lab",
            (f("mode", "Mode", "select", choices=("list", "verify"), default="list"), f("limit", "Limit", "number", default=200, minimum=1, maximum=10000)),
        ),
        Operation("lab_status", "Lab status", "Show enrolled agents, pools, queued jobs and audit integrity.", "Lab"),
        Operation("lab_agents", "Lab agents", "List enrolled remote lab agents and current capabilities.", "Lab"),
        Operation(
            "lab_agent_enroll", "Enroll lab agent", "Issue an mTLS client certificate and one-time agent token.", "Lab",
            (f("name", "Agent name", required=True), f("pki_dir", "PKI directory", required=True), f("controller", "Controller HTTPS URL", required=True)), destructive=True,
        ),
        Operation(
            "lab_pool_manage", "Manage lab pools", "Create pools or add enrolled agent/device members.", "Lab",
            (f("mode", "Mode", "select", choices=("list","create","add"), default="list"), f("name", "Pool name"), f("pool", "Pool ID/name"), f("agent", "Agent ID/name"), f("device", "Device serial")), destructive=True,
        ),
        Operation("lab_pools", "Lab pools", "List device pools and pool membership.", "Lab"),
        Operation("lab_jobs", "Lab jobs", "List distributed lab jobs.", "Lab", (f("limit", "Limit", "number", default=200, minimum=1, maximum=5000),)),
        Operation(
            "lab_job_submit", "Submit lab job",
            "Queue an allowlisted operation for an enrolled outbound-only agent.",
            "Lab",
            (
                f("agent", "Agent ID or name", required=True), f("action", "Allowlisted operation", required=True),
                f("payload", "JSON payload", "textarea", default="{}"), f("role", "Requester role", "select", choices=("viewer", "analyst", "operator", "administrator"), default="operator"),
                f("actor", "Requester", default="local-operator"), f("approved", "Explicit approval", "boolean", default=False),
            ),
            destructive=True,
        ),
        Operation(
            "lab_job_cancel", "Cancel lab job", "Cancel a queued or running distributed job.", "Lab",
            (f("job_id", "Job ID", required=True),), destructive=True,
        ),
        Operation(
            "lab_pool_submit", "Submit pool job", "Queue an allowlisted operation across all members of a device pool.", "Lab",
            (f("pool", "Pool ID or name", required=True), f("action", "Allowlisted operation", required=True), f("payload", "JSON payload", "textarea", default="{}"), f("role", "Requester role", "select", choices=("viewer","analyst","operator","administrator"), default="operator"), f("actor", "Requester", default="local-operator"), f("approved", "Explicit approval", "boolean", default=False)), destructive=True,
        ),
        Operation(
            "plugin_keygen", "Plugin signing keypair", "Generate an Ed25519 publisher signing keypair.", "Extensions",
            (f("private_key", "Private key output", required=True), f("public_key", "Public key output", required=True)), destructive=True,
        ),
        Operation(
            "plugin_sign", "Sign plugin", "Sign a plugin manifest and file with an Ed25519 publisher key.", "Extensions",
            (f("manifest", "Manifest JSON", "file", required=True), f("plugin_file", "Plugin file", "file", required=True), f("private_key", "Private key", "file", required=True), f("output", "Signature bundle output", required=True)), destructive=True,
        ),
        Operation(
            "plugin_publisher", "Plugin publishers", "List, trust, or revoke Ed25519 plugin publishers.", "Extensions",
            (f("mode", "Mode", "select", choices=("list","add","revoke"), default="list"), f("name", "Publisher name"), f("public_key", "Publisher public key", "file")), destructive=True,
        ),
        Operation(
            "plugin_verify_trusted", "Verify trusted plugin", "Verify a signed plugin against a non-revoked trusted publisher.", "Extensions",
            (f("bundle", "Signature bundle JSON", "file", required=True), f("plugin_file", "Plugin file", "file", required=True), f("publisher", "Trusted publisher", required=True)),
        ),
        Operation(
            "governance", "Evidence governance", "Apply legal holds or AES-256-GCM seal/unseal sensitive evidence.", "Evidence",
            (f("mode", "Mode", "select", choices=("holds","hold","release","seal","unseal"), default="holds"), f("project_id", "Project ID"), f("reason", "Hold reason"), f("actor", "Actor", default="local-operator"), f("path", "Input file", "file"), f("output", "Output file"), f("passphrase", "Vault passphrase", "secret")), destructive=True,
        ),
        Operation(
            "plugin_verify", "Verify signed plugin", "Verify an Ed25519 signed plugin bundle and trusted publisher key.", "Extensions",
            (f("bundle", "Signature bundle JSON", "file", required=True), f("plugin_file", "Plugin file", "file", required=True), f("public_key", "Publisher public key", "file", required=True)),
        ),
        Operation(
            "sbom_generate", "Generate SBOM", "Generate a CycloneDX or SPDX runtime software bill of materials.", "System",
            (f("format", "Format", "select", choices=("cyclonedx", "spdx"), default="cyclonedx"), f("output", "Output file", required=True)),
        ),
    ]
    for item in additions:
        module.OPERATIONS[item.name] = item
    module.WEB_ACTIONS = frozenset(module.OPERATIONS)
