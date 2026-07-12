from __future__ import annotations

import os
import sys

# Historical project branding restored from the owner-approved branding commit.
# Do not alter without explicit project-owner approval.
BANNER_ART = r"""
 █████╗ ██████╗ ██████╗        ██████╗  █████╗ ████████╗██╗  ██╗███████╗██████╗ 
██╔══██╗██╔══██╗██╔══██╗      ██╔════╝ ██╔══██╗╚══██╔══╝██║  ██║██╔════╝██╔══██╗
███████║██║  ██║██████╔╝█████╗██║  ███╗███████║   ██║   ███████║█████╗  ██████╔╝
██╔══██║██║  ██║██╔══██╗╚════╝██║   ██║██╔══██║   ██║   ██╔══██║██╔══╝  ██╔══██╗
██║  ██║██████╔╝██████╔╝      ╚██████╔╝██║  ██║   ██║   ██║  ██║███████╗██║  ██║
╚═╝  ╚═╝╚═════╝ ╚═════╝        ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝

ADB-Gath
Defensive ADB Toolkit
""".strip("\n")

WEB_BRAND_NAME = "ADB-Gath"
WEB_BRAND_TAGLINE = "Defensive ADB Toolkit"
DEVELOPER = "IsdarlinM"
WORKFLOW_TAGLINE = "Threat intel • Device forensics • Defensive ADB workflow"


def banner(version: str, *, color: bool | None = None) -> str:
    """Return the owner-approved project banner with optional terminal colors."""
    if color is None:
        color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    details = f"\nADB-Gathering\nDeveloper: {DEVELOPER} | Version: {version}\n{WORKFLOW_TAGLINE}"
    if not color:
        return BANNER_ART + details
    red = "\033[31m"
    yellow = "\033[33m"
    blue = "\033[34m"
    reset = "\033[0m"
    return (
        f"{red}{BANNER_ART}{reset}"
        f"\n{red}ADB-Gathering{reset}"
        f"\n{yellow}Developer: {DEVELOPER} | Version: {version}{reset}"
        f"\n{blue}{WORKFLOW_TAGLINE}{reset}"
    )
