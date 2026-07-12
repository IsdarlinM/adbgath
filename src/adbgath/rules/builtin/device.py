from __future__ import annotations

from .. import Finding, engine

REFS = ("OWASP MASVS-RESILIENCE", "OWASP MASTG", "CWE-284")


@engine.register
def selinux_not_enforcing(context):
    value = str(context.get("selinux", "")).strip()
    if value.lower() == "enforcing":
        return None
    return Finding(
        "ANDROID-DEVICE-SELINUX-001",
        "SELinux is not enforcing",
        "high",
        "high",
        "The device reports an SELinux mode other than Enforcing.",
        value or "No SELinux state returned",
        "A permissive or disabled policy weakens mandatory access controls and can make local compromise easier to escalate.",
        "Use a production build with SELinux Enforcing and investigate policy denials rather than disabling enforcement.",
        references=REFS,
    )


@engine.register
def verified_boot(context):
    value = str(context.get("verified_boot", "")).strip().lower()
    if value in {"green", "locked"}:
        return None
    return Finding(
        "ANDROID-DEVICE-BOOT-001",
        "Verified Boot is not in a trusted state",
        "high",
        "high",
        "The boot verification state is not reported as green/locked.",
        value or "No verified boot state returned",
        "An unlocked or unverified boot chain can permit modified system images and invalidates some security assumptions.",
        "Use a locked bootloader and a trusted production image for security validation unless an intentionally rooted lab is required.",
        references=("Android Verified Boot", "OWASP MASTG-ENV"),
    )


@engine.register
def debuggable_build(context):
    if str(context.get("ro_debuggable", "0")).strip() != "1":
        return None
    return Finding(
        "ANDROID-DEVICE-DEBUG-001",
        "Device build is globally debuggable",
        "high",
        "high",
        "The ro.debuggable property is enabled.",
        f"ro.debuggable={context.get('ro_debuggable')}",
        "Debug-enabled system images may expose privileged diagnostics and behavior not present on production devices.",
        "Repeat security conclusions on a production-equivalent user build and restrict debug images to controlled labs.",
        references=("Android build variants", "OWASP MASTG-ENV"),
    )


@engine.register
def insecure_ro_secure(context):
    if str(context.get("ro_secure", "1")).strip() != "0":
        return None
    return Finding(
        "ANDROID-DEVICE-ADBD-001",
        "ADB secure mode is disabled",
        "high",
        "high",
        "The ro.secure property is disabled.",
        f"ro.secure={context.get('ro_secure')}",
        "The ADB daemon may run with weaker privilege separation than expected on production devices.",
        "Use a production user build with secure ADB configuration.",
        references=("Android Debug Bridge", "CWE-250"),
    )


@engine.register
def proxy_configured(context):
    value = str(context.get("http_proxy", "")).strip()
    if value in {"", ":0", "null", "none"}:
        return None
    return Finding(
        "ANDROID-DEVICE-PROXY-001",
        "Global HTTP proxy is configured",
        "medium",
        "high",
        "The device has a global proxy configured.",
        value,
        "Traffic can be redirected through an interception point; this may be intended in a lab but affects evidence interpretation.",
        "Document the proxy as part of test conditions and clear it after authorized testing.",
        references=("OWASP MASTG-NETWORK",),
    )
