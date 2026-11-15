"""Tests for binary probe and capability detection (FR-EXEC-6)."""

import os
from pathlib import Path

from hwq.exec.probe import (
    DESIRED_LSBLK_COLUMNS,
    MINIMAL_LSBLK_COLUMNS,
    TRUSTED_DIRS,
    check_command_available,
    find_binary,
    parse_lsblk_columns,
    select_lsblk_columns,
)


def test_trusted_dirs_pinned() -> None:
    """Trusted directories must be fixed and contain standard Linux bin paths."""
    assert TRUSTED_DIRS == ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def test_find_binary_in_custom_dirs(tmp_path: Path) -> None:
    """find_binary finds an executable in provided trusted directories."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_lscpu = bin_dir / "lscpu"
    fake_lscpu.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    # Mark executable if on POSIX
    if hasattr(os, "chmod"):
        os.chmod(fake_lscpu, 0o755)

    found = find_binary("lscpu", search_dirs=[str(bin_dir)])
    assert found is not None
    assert found.endswith("/bin/lscpu")
    assert check_command_available("lscpu", search_dirs=[str(bin_dir)]) is True


def test_find_binary_not_found(tmp_path: Path) -> None:
    """find_binary returns None if executable does not exist."""
    found = find_binary("nonexistent_tool", search_dirs=[str(tmp_path)])
    assert found is None
    assert check_command_available("nonexistent_tool", search_dirs=[str(tmp_path)]) is False


def test_find_binary_rejects_path_traversal() -> None:
    """find_binary rejects strings containing slashes or directory traversal."""
    assert find_binary("../bin/sh") is None
    assert find_binary("/bin/sh") is None
    assert find_binary("sub/tool") is None


def test_parse_lsblk_columns() -> None:
    """parse_lsblk_columns parses standard `lsblk --list-columns` output."""
    raw_sample = """COLUMN DESCRIPTION
NAME   device name
TYPE   device type
SIZE   size of the device
MODEL  device identifier
ROTA   rotational device
TRAN   device transport type
RM     removable device
HOTPLUG removable or hotplug device
"""
    cols = parse_lsblk_columns(raw_sample)
    assert "NAME" in cols
    assert "TYPE" in cols
    assert "SIZE" in cols
    assert "MODEL" in cols
    assert "ROTA" in cols
    assert "TRAN" in cols
    assert "RM" in cols
    assert "HOTPLUG" in cols
    assert "COLUMN" not in cols  # Header omitted


def test_select_lsblk_columns_all_supported() -> None:
    """select_lsblk_columns retains all columns when supported."""
    available = set(DESIRED_LSBLK_COLUMNS)
    selected = select_lsblk_columns(available)
    assert selected == DESIRED_LSBLK_COLUMNS


def test_select_lsblk_columns_degraded() -> None:
    """select_lsblk_columns drops unsupported columns like HOTPLUG and TRAN."""
    available = {"NAME", "TYPE", "SIZE", "MODEL", "ROTA"}
    selected = select_lsblk_columns(available)
    assert selected == ("NAME", "TYPE", "SIZE", "MODEL", "ROTA")
    assert "HOTPLUG" not in selected
    assert "TRAN" not in selected


def test_select_lsblk_columns_empty_fallback() -> None:
    """select_lsblk_columns falls back to minimal columns if empty."""
    selected = select_lsblk_columns(set())
    assert selected == MINIMAL_LSBLK_COLUMNS
