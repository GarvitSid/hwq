"""Tests for privilege management and sudoers validation (FR-PRIV-1, FR-PRIV-2)."""

import pytest

from hwq.exec.privilege import (
    build_privileged_cmd,
    generate_sudoers_rule,
    is_root,
    validate_sudoers_rule,
)
from hwq.models import CommandSpec


def test_is_root_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_root returns False on non-POSIX / Windows without raising."""
    monkeypatch.delattr("os.geteuid", raising=False)
    assert is_root() is False


def test_is_root_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_root correctly reflects geteuid return value."""
    monkeypatch.setattr("os.geteuid", lambda: 0, raising=False)
    assert is_root() is True

    monkeypatch.setattr("os.geteuid", lambda: 1000, raising=False)
    assert is_root() is False


def test_build_privileged_cmd_valid() -> None:
    """Valid dmidecode -t memory wraps into exact sudo -n argv."""
    spec = CommandSpec(argv=("dmidecode", "-t", "memory"), privileged=True)
    priv_spec = build_privileged_cmd(spec)
    assert priv_spec.argv == (
        "/usr/bin/sudo",
        "-n",
        "/usr/sbin/dmidecode",
        "-t",
        "memory",
    )
    assert priv_spec.privileged is True


def test_build_privileged_cmd_unprivileged_spec() -> None:
    """Attempting to elevate an unprivileged spec raises ValueError."""
    spec = CommandSpec(argv=("dmidecode", "-t", "memory"), privileged=False)
    with pytest.raises(ValueError, match="Cannot elevate an unprivileged"):
        build_privileged_cmd(spec)


def test_build_privileged_cmd_forbidden_binary() -> None:
    """Attempting to elevate any binary other than dmidecode raises ValueError."""
    spec = CommandSpec(argv=("lscpu", "-J"), privileged=True)
    with pytest.raises(ValueError, match="Privilege elevation forbidden"):
        build_privileged_cmd(spec)


def test_build_privileged_cmd_forbidden_args() -> None:
    """Attempting to elevate dmidecode with modified args raises ValueError."""
    # Extra arguments
    spec1 = CommandSpec(
        argv=("dmidecode", "-t", "memory", "-s", "system-serial-number"),
        privileged=True,
    )
    with pytest.raises(ValueError, match="Privilege elevation arguments forbidden"):
        build_privileged_cmd(spec1)

    # Different type (e.g. bios)
    spec2 = CommandSpec(argv=("dmidecode", "-t", "bios"), privileged=True)
    with pytest.raises(ValueError, match="Privilege elevation arguments forbidden"):
        build_privileged_cmd(spec2)

    # No arguments
    spec3 = CommandSpec(argv=("dmidecode",), privileged=True)
    with pytest.raises(ValueError, match="Privilege elevation arguments forbidden"):
        build_privileged_cmd(spec3)


def test_generate_sudoers_rule_default() -> None:
    """generate_sudoers_rule generates exact pinned drop-in rule."""
    rule = generate_sudoers_rule("testuser", "/usr/sbin/dmidecode")
    assert rule == "testuser ALL=(root) NOPASSWD: /usr/sbin/dmidecode -t memory"
    assert validate_sudoers_rule(rule) is True


def test_generate_sudoers_rule_rejections() -> None:
    """generate_sudoers_rule rejects wildcards and dangerous characters."""
    with pytest.raises(ValueError, match="Invalid username"):
        generate_sudoers_rule("bad user; rm -rf")

    with pytest.raises(ValueError, match="Invalid absolute binary path"):
        generate_sudoers_rule("user", "dmidecode")

    with pytest.raises(ValueError, match="Invalid absolute binary path"):
        generate_sudoers_rule("user", "/usr/sbin/*")


def test_validate_sudoers_rule_checks() -> None:
    """validate_sudoers_rule catches invalid, wildcarded, or loose rules."""
    assert validate_sudoers_rule("user ALL=(root) NOPASSWD: /usr/sbin/dmidecode -t memory") is True
    assert validate_sudoers_rule("user ALL=(root) NOPASSWD: /usr/bin/dmidecode -t memory") is True

    # Bad rules
    assert validate_sudoers_rule("user ALL=(root) NOPASSWD: /usr/sbin/dmidecode *") is False
    assert validate_sudoers_rule("user ALL=(root) NOPASSWD: /usr/sbin/dmidecode") is False
    assert validate_sudoers_rule("user ALL=(root) NOPASSWD: dmidecode -t memory") is False
    assert validate_sudoers_rule("user ALL=(ALL) ALL") is False
    assert validate_sudoers_rule("user ALL=(root) NOPASSWD: /bin/bash") is False
