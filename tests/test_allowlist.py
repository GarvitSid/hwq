"""Tests for allow-list registry and security auditing (FR-EXEC-4, FR-PRIV-4)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hwq.exec.allowlist import (
    ALLOWED_COMMANDS,
    ALLOWED_FILES,
    FORBIDDEN_BINARIES,
    get_command_spec,
    is_allowlisted_command,
    is_allowlisted_file,
    list_allowlisted_commands,
    list_allowlisted_files,
)
from hwq.models import CommandSpec

READONLY_BINARIES = frozenset({"lscpu", "dmidecode", "lsblk", "lspci", "nvidia-smi"})


def test_allowlist_audit_binaries() -> None:
    """FR-EXEC-4: Ensure only verified read-only binaries exist in the registry."""
    for key, spec in ALLOWED_COMMANDS.items():
        binary = spec.argv[0]
        assert binary in READONLY_BINARIES, (
            f"Command '{key}' uses unapproved binary '{binary}'"
        )
        assert binary not in FORBIDDEN_BINARIES, (
            f"Command '{key}' uses forbidden binary '{binary}'"
        )


def test_allowlist_audit_privileged_count() -> None:
    """FR-PRIV-1: Exactly ONE command may be privileged ('dmidecode -t memory')."""
    privileged_specs = [s for s in ALLOWED_COMMANDS.values() if s.privileged]
    assert len(privileged_specs) == 1, (
        f"Expected exactly 1 privileged command, found {len(privileged_specs)}"
    )
    assert privileged_specs[0].argv == ("dmidecode", "-t", "memory")


def test_allowlist_audit_flags_and_arguments() -> None:
    """Audit command arguments for write flags or shell metacharacters."""
    dangerous_chars = {";", "|", "&", "$", "`", ">", "<", "\n", "\r"}
    for key, spec in ALLOWED_COMMANDS.items():
        for arg in spec.argv:
            for char in dangerous_chars:
                assert char not in arg, (
                    f"Dangerous character '{char}' in arg '{arg}' of command '{key}'"
                )
            # Ensure no serial/UUID flags are passed to dmidecode
            if spec.argv[0] == "dmidecode":
                assert "-s" not in spec.argv
                assert "serial" not in " ".join(spec.argv).lower()
                assert "uuid" not in " ".join(spec.argv).lower()


def test_allowlist_audit_file_paths() -> None:
    """FR-PRIV-4: Ensure no serial/UUID/asset file paths exist in the file allow-list."""
    for path in ALLOWED_FILES:
        lower = path.lower()
        assert "serial" not in lower, f"Serial number path in allow-list: {path}"
        assert "uuid" not in lower, f"UUID path in allow-list: {path}"
        assert "asset" not in lower, f"Asset tag path in allow-list: {path}"
        assert path.startswith(("/sys/", "/etc/", "/proc/")), (
            f"Unexpected file path prefix: {path}"
        )


def test_is_allowlisted_command_exact_matching() -> None:
    """is_allowlisted_command matches exact registered specs only."""
    valid_spec = get_command_spec("cpu_lscpu")
    assert is_allowlisted_command(valid_spec) is True

    # Mutated argv
    tampered_argv = CommandSpec(argv=("lscpu", "-a"))
    assert is_allowlisted_command(tampered_argv) is False

    # Mutated privilege
    tampered_priv = CommandSpec(argv=("lscpu", "-J"), privileged=True)
    assert is_allowlisted_command(tampered_priv) is False


def test_is_allowlisted_file_boundaries() -> None:
    """is_allowlisted_file approves valid paths and rejects arbitrary or serial paths."""
    assert is_allowlisted_file("/proc/meminfo") is True
    assert is_allowlisted_file("/etc/os-release") is True
    assert is_allowlisted_file("/sys/class/dmi/id/product_name") is True

    # Rejection of sensitive paths
    assert is_allowlisted_file("/etc/shadow") is False
    assert is_allowlisted_file("/etc/passwd") is False
    assert is_allowlisted_file("/sys/class/dmi/id/product_serial") is False
    assert is_allowlisted_file("/sys/class/dmi/id/product_uuid") is False
    assert is_allowlisted_file("/sys/class/dmi/id/chassis_asset_tag") is False


def test_get_command_spec_invalid_key() -> None:
    """get_command_spec raises KeyError on unknown key."""
    with pytest.raises(KeyError, match="not in the allow-list"):
        get_command_spec("unknown_command")


@given(st.text())
def test_fuzz_command_lookup(lookup_key: str) -> None:
    """Fuzz testing: random string lookups either return valid spec or raise KeyError."""
    if lookup_key in ALLOWED_COMMANDS:
        spec = get_command_spec(lookup_key)
        assert isinstance(spec, CommandSpec)
    else:
        with pytest.raises(KeyError):
            get_command_spec(lookup_key)


def test_list_allowlisted_helpers() -> None:
    """list_allowlisted_commands and list_allowlisted_files return correct structures."""
    commands = list_allowlisted_commands()
    assert len(commands) == len(ALLOWED_COMMANDS)
    assert all(isinstance(c, CommandSpec) for c in commands)

    files = list_allowlisted_files()
    assert len(files) == len(ALLOWED_FILES)
    assert "/proc/meminfo" in files
