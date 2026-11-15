"""Privilege management and sudo wrapper (SRS 4.4, FR-PRIV-1, FR-PRIV-2).

All modules in hwq.exec must remain stdlib-only.
"""

from __future__ import annotations

import os
import re

from hwq.models import CommandSpec

# Pinned command signature that may be elevated
ALLOWED_PRIVILEGED_ARGS = ("-t", "memory")
SUDOERS_REGEX = re.compile(
    r"^[a-zA-Z0-9_.-]+\s+ALL=\(root\)\s+NOPASSWD:\s+(/[a-zA-Z0-9_./-]+)\s+-t\s+memory$"
)
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+$")


def is_root() -> bool:
    """Check if the current process runs with root privileges.

    Windows-safe: avoids direct os.geteuid call where unavailable.
    """
    geteuid_fn = getattr(os, "geteuid", None)
    if geteuid_fn is not None:
        try:
            return bool(geteuid_fn() == 0)
        except Exception:
            return False
    return False


def build_privileged_cmd(
    spec: CommandSpec,
    sudo_path: str = "/usr/bin/sudo",
    dmidecode_path: str = "/usr/sbin/dmidecode",
) -> CommandSpec:
    """Build exact sudo -n command for privileged execution.

    Only 'dmidecode -t memory' is permitted to run privileged (FR-PRIV-1).
    Raises ValueError if any other command or argument variation is supplied.
    """
    if not spec.privileged:
        raise ValueError("Cannot elevate an unprivileged CommandSpec")

    # Verify command is dmidecode with exact pinned arguments
    base_cmd = os.path.basename(spec.argv[0])
    if base_cmd != "dmidecode":
        raise ValueError(
            f"Privilege elevation forbidden for '{spec.argv[0]}'. "
            "Only 'dmidecode -t memory' may run privileged."
        )

    if spec.argv[1:] != ALLOWED_PRIVILEGED_ARGS:
        raise ValueError(
            f"Privilege elevation arguments forbidden: {spec.argv[1:]!r}. "
            f"Expected exact args: {ALLOWED_PRIVILEGED_ARGS!r}."
        )

    privileged_argv = (sudo_path, "-n", dmidecode_path, "-t", "memory")
    return CommandSpec(
        argv=privileged_argv,
        privileged=True,
        timeout_s=spec.timeout_s,
        max_bytes=spec.max_bytes,
    )


def generate_sudoers_rule(
    username: str = "youruser",
    dmidecode_path: str = "/usr/sbin/dmidecode",
) -> str:
    """Generate exact, pinned sudoers drop-in line (SRS Appendix B)."""
    clean_user = username.strip()
    clean_path = dmidecode_path.strip()

    if not USERNAME_REGEX.match(clean_user):
        raise ValueError(f"Invalid username for sudoers rule: {username!r}")
    if not clean_path.startswith("/") or "*" in clean_path or "?" in clean_path:
        raise ValueError(f"Invalid absolute binary path for sudoers rule: {dmidecode_path!r}")

    rule = f"{clean_user} ALL=(root) NOPASSWD: {clean_path} -t memory"
    if not validate_sudoers_rule(rule):
        raise ValueError(f"Generated sudoers rule failed safety validation: {rule}")
    return rule


def validate_sudoers_rule(rule: str) -> bool:
    """Verify that a sudoers rule has no wildcards, no bare paths, and pinned args."""
    clean = rule.strip()
    if "*" in clean or "?" in clean or "~" in clean:
        return False
    match = SUDOERS_REGEX.match(clean)
    if not match:
        return False
    binary_path = match.group(1)
    if not binary_path.startswith("/"):
        return False
    return True
