"""Tests for subprocess runner and system file reader.

Requirements: FR-EXEC-1, FR-EXEC-2, FR-EXEC-3, FR-EXEC-5.
"""

import sys
from pathlib import Path

from hwq.exec.runner import (
    DEFAULT_SAFE_ENV,
    get_execution_env,
    read_system_file,
    run_command,
)
from hwq.models import CommandSpec


def test_default_safe_env() -> None:
    """DEFAULT_SAFE_ENV contains LC_ALL=C and fixed PATH."""
    assert DEFAULT_SAFE_ENV["LC_ALL"] == "C"
    assert DEFAULT_SAFE_ENV["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"

    env = get_execution_env()
    assert env["LC_ALL"] == "C"


def test_run_command_success() -> None:
    """run_command executes command and captures stdout cleanly."""
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; sys.stdout.write('hardware facts')"),
        privileged=False,
    )
    result = run_command(spec)
    assert result.status == "ok"
    assert result.exit_code == 0
    assert result.stdout == "hardware facts"
    assert result.stderr == ""


def test_run_command_output_cap() -> None:
    """run_command enforces output cap max_bytes."""
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; sys.stdout.write('A' * 2000)"),
        max_bytes=100,
    )
    result = run_command(spec)
    assert result.status == "ok"
    assert len(result.stdout) == 100
    assert result.stdout == "A" * 100


def test_run_command_timeout() -> None:
    """run_command maps TimeoutExpired to status timeout and exit_code -1."""
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import time; time.sleep(2)"),
        timeout_s=0.2,
    )
    result = run_command(spec)
    assert result.status == "timeout"
    assert result.exit_code == -1
    assert "timed out" in result.stderr


def test_run_command_missing_binary() -> None:
    """run_command maps FileNotFoundError to status unavailable and exit_code 127."""
    spec = CommandSpec(argv=("this_tool_does_not_exist_xyz123",))
    result = run_command(spec)
    assert result.status == "unavailable"
    assert result.exit_code == 127
    assert "not found" in result.stderr


def test_run_command_error_exit() -> None:
    """run_command maps general non-zero exit code to status error."""
    spec = CommandSpec(
        argv=(sys.executable, "-c", "import sys; sys.stderr.write('fatal'); sys.exit(1)"),
    )
    result = run_command(spec)
    assert result.status == "error"
    assert result.exit_code == 1
    assert "fatal" in result.stderr


def test_run_command_permission_denied_stderr() -> None:
    """run_command maps permission denied in stderr to status permission_denied."""
    spec = CommandSpec(
        argv=(
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('Permission denied'); sys.exit(1)",
        ),
    )
    result = run_command(spec)
    assert result.status == "permission_denied"


def test_read_system_file_success(tmp_path: Path) -> None:
    """read_system_file reads file content and normalizes CRLF to LF."""
    test_file = tmp_path / "sys_test.txt"
    test_file.write_bytes(b"line1\r\nline2\n")

    result = read_system_file(str(test_file), enforce_allowlist=False)
    assert result.status == "ok"
    assert result.exit_code == 0
    assert result.stdout == "line1\nline2\n"


def test_read_system_file_truncation(tmp_path: Path) -> None:
    """read_system_file caps reading at max_bytes."""
    test_file = tmp_path / "large_file.txt"
    test_file.write_bytes(b"X" * 500)

    result = read_system_file(str(test_file), max_bytes=50, enforce_allowlist=False)
    assert result.status == "ok"
    assert len(result.stdout) == 50
    assert "truncated" in result.stderr


def test_read_system_file_not_found() -> None:
    """read_system_file returns unavailable for missing file."""
    result = read_system_file("/sys/class/dmi/id/nonexistent_xyz", enforce_allowlist=False)
    assert result.status == "unavailable"
    assert result.exit_code == 1


def test_read_system_file_disallowed_path() -> None:
    """read_system_file blocks paths not in allowlist when enforce_allowlist=True."""
    result = read_system_file("/etc/shadow", enforce_allowlist=True)
    assert result.status == "permission_denied"
    assert "not permitted by allow-list" in result.stderr
