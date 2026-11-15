"""Allow-listed command and file registry (SRS 4.3, 5, FR-EXEC-4).

All modules in hwq.exec must remain stdlib-only.
"""

from __future__ import annotations

from typing import Final

from hwq.models import CommandSpec

# Pinned immutable command specifications (FR-EXEC-1, FR-EXEC-4)
ALLOWED_COMMANDS: Final[dict[str, CommandSpec]] = {
    "cpu_lscpu": CommandSpec(
        argv=("lscpu", "-J"),
        privileged=False,
        timeout_s=5.0,
        max_bytes=1_048_576,
    ),
    "memory_dmi": CommandSpec(
        argv=("dmidecode", "-t", "memory"),
        privileged=True,
        timeout_s=5.0,
        max_bytes=1_048_576,
    ),
    "storage_lsblk": CommandSpec(
        argv=(
            "lsblk",
            "-J",
            "-b",
            "-d",
            "-o",
            "NAME,TYPE,SIZE,MODEL,ROTA,TRAN,RM,HOTPLUG",
        ),
        privileged=False,
        timeout_s=5.0,
        max_bytes=1_048_576,
    ),
    "storage_lsblk_probe": CommandSpec(
        argv=("lsblk", "--list-columns"),
        privileged=False,
        timeout_s=5.0,
        max_bytes=65_536,
    ),
    "gpu_lspci": CommandSpec(
        argv=("lspci", "-mm", "-nn"),
        privileged=False,
        timeout_s=5.0,
        max_bytes=1_048_576,
    ),
    "gpu_nvidia": CommandSpec(
        argv=(
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ),
        privileged=False,
        timeout_s=5.0,
        max_bytes=65_536,
    ),
}

# Pinned allow-listed native file paths for get_system_overview and get_memory_summary
ALLOWED_FILES: Final[frozenset[str]] = frozenset({
    "/sys/class/dmi/id/sys_vendor",
    "/sys/class/dmi/id/product_name",
    "/sys/class/dmi/id/bios_vendor",
    "/sys/class/dmi/id/bios_version",
    "/sys/class/dmi/id/bios_date",
    "/sys/class/dmi/id/board_vendor",
    "/sys/class/dmi/id/board_name",
    "/etc/os-release",
    "/proc/sys/kernel/osrelease",
    "/proc/meminfo",
})

# Forbidden commands, destructive binaries, and write flags for allow-list auditing
FORBIDDEN_BINARIES: Final[frozenset[str]] = frozenset({
    "rm",
    "sh",
    "bash",
    "dash",
    "zsh",
    "python",
    "perl",
    "ruby",
    "dd",
    "mkfs",
    "fdisk",
    "parted",
    "reboot",
    "poweroff",
    "shutdown",
    "kill",
    "pkill",
    "curl",
    "wget",
    "nc",
    "netcat",
    "chmod",
    "chown",
})

FORBIDDEN_FLAG_FRAGMENTS: Final[frozenset[str]] = frozenset({
    "-w",
    "--write",
    "--delete",
    "--remove",
    "--modify",
    "--set",
    "--format",  # exception: nvidia-smi --format=csv is checked explicitly
    "--output-file",
})


def get_command_spec(key: str) -> CommandSpec:
    """Retrieve an immutable allow-listed CommandSpec by registry key."""
    if key not in ALLOWED_COMMANDS:
        raise KeyError(f"Command '{key}' is not in the allow-list registry")
    return ALLOWED_COMMANDS[key]


def is_allowlisted_command(spec: CommandSpec) -> bool:
    """Check if a CommandSpec exactly matches a registered allow-listed command."""
    for registered in ALLOWED_COMMANDS.values():
        if (
            registered.argv == spec.argv
            and registered.privileged == spec.privileged
            and registered.timeout_s == spec.timeout_s
            and registered.max_bytes == spec.max_bytes
        ):
            return True
    return False


def is_allowlisted_file(path: str) -> bool:
    """Check if a file path is permitted for native reading."""
    clean_path = path.strip().replace("\\", "/")
    # Reject paths containing serial or uuid tokens
    lower_path = clean_path.lower()
    if "serial" in lower_path or "uuid" in lower_path:
        return False
    return clean_path in ALLOWED_FILES


def list_allowlisted_commands() -> list[CommandSpec]:
    """Return all allow-listed CommandSpecs."""
    return list(ALLOWED_COMMANDS.values())


def list_allowlisted_files() -> list[str]:
    """Return all allow-listed native file paths."""
    return sorted(ALLOWED_FILES)
