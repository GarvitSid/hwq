"""Trusted binary discovery and capability probe (SRS 4.3, FR-EXEC-6).

All modules in hwq.exec must remain stdlib-only.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

# Fixed trusted directories for binary discovery (FR-EXEC-6)
TRUSTED_DIRS: tuple[str, ...] = (
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)

# Standard lsblk columns desired by get_storage_devices
DESIRED_LSBLK_COLUMNS: tuple[str, ...] = (
    "NAME",
    "TYPE",
    "SIZE",
    "MODEL",
    "ROTA",
    "TRAN",
    "RM",
    "HOTPLUG",
)

MINIMAL_LSBLK_COLUMNS: tuple[str, ...] = (
    "NAME",
    "TYPE",
    "SIZE",
)


def find_binary(
    name: str,
    search_dirs: Iterable[str] | None = None,
) -> str | None:
    """Discover the absolute path of a binary using only fixed trusted directories.

    Never searches the user's PATH variable (FR-EXEC-6).
    Returns None if not found or not executable.
    """
    clean_name = os.path.basename(name.strip())
    if not clean_name or clean_name != name.strip():
        # Reject names containing path traversal or directory components
        return None

    dirs = search_dirs if search_dirs is not None else TRUSTED_DIRS

    for directory in dirs:
        candidate = os.path.join(directory, clean_name)
        # Normalize to forward slashes for target system paths
        posix_candidate = candidate.replace("\\", "/")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return posix_candidate

    return None


def check_command_available(
    name: str,
    search_dirs: Iterable[str] | None = None,
) -> bool:
    """Check if a trusted command binary exists and is executable."""
    return find_binary(name, search_dirs=search_dirs) is not None


def parse_lsblk_columns(raw_output: str) -> set[str]:
    """Parse output of `lsblk --list-columns` into a set of uppercase column names."""
    columns: set[str] = set()
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        # lsblk --list-columns outputs header "COLUMN DESCRIPTION" or single names
        parts = line.split()
        first_token = parts[0].upper()
        if first_token in ("COLUMN", "NAME", "HEADER"):
            if first_token == "COLUMN":
                # Header row: COLUMN DESCRIPTION
                continue
        # Extract column identifier
        columns.add(first_token)
    return columns


def select_lsblk_columns(
    available_columns: set[str],
    desired_columns: tuple[str, ...] = DESIRED_LSBLK_COLUMNS,
) -> tuple[str, ...]:
    """Select supported lsblk columns from desired columns.

    Degrades gracefully if some columns (e.g. HOTPLUG or TRAN) are unsupported
    in older util-linux releases.
    """
    selected = [col for col in desired_columns if col in available_columns]
    # Ensure at least minimal columns if available
    if not selected:
        return MINIMAL_LSBLK_COLUMNS
    return tuple(selected)
