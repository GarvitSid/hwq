"""Safe subprocess runner and native file reader (SRS 4.3).

Requirements: FR-EXEC-1, FR-EXEC-2, FR-EXEC-3, FR-EXEC-5.
All modules in hwq.exec must remain stdlib-only.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Mapping

from hwq.exec.allowlist import is_allowlisted_file
from hwq.models import CommandSpec, ExecutionStatus, RawResult

# Fixed sanitized environment for execution (FR-EXEC-2)
DEFAULT_SAFE_ENV: dict[str, str] = {
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
}


def get_execution_env(custom_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build isolated environment with LC_ALL=C and trusted PATH."""
    env = dict(DEFAULT_SAFE_ENV)
    if custom_env is not None:
        env.update(custom_env)
    # Ensure critical Windows variables remain if running on Windows
    if os.name == "nt":
        for win_var in ("SystemRoot", "WINDIR", "PATHEXT"):
            if win_var in os.environ and win_var not in env:
                env[win_var] = os.environ[win_var]
    return env


def run_command(
    spec: CommandSpec,
    *,
    custom_env: Mapping[str, str] | None = None,
) -> RawResult:
    """Execute a CommandSpec with bounded resources and strict sandboxing.

    Enforces:
    - shell=False (never dynamic strings)
    - stdin=DEVNULL
    - timeout=spec.timeout_s
    - output cap=spec.max_bytes
    - status mapping per FR-EXEC-3
    """
    env = get_execution_env(custom_env)
    start_time = time.monotonic()

    try:
        proc = subprocess.Popen(
            list(spec.argv),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        try:
            raw_stdout, raw_stderr = proc.communicate(timeout=spec.timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            duration = time.monotonic() - start_time
            return RawResult(
                argv=spec.argv,
                exit_code=-1,
                stdout="",
                stderr="Execution timed out",
                status="timeout",
                duration_s=duration,
            )

        duration = time.monotonic() - start_time
        exit_code = proc.returncode

        # Enforce output cap (max_bytes)
        stdout = raw_stdout[: spec.max_bytes].decode("utf-8", errors="replace")
        stderr = raw_stderr[: spec.max_bytes].decode("utf-8", errors="replace")

        # Map exit status
        status: ExecutionStatus = "ok"
        if exit_code != 0:
            status = _map_exit_status(exit_code, stderr)

        return RawResult(
            argv=spec.argv,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            status=status,
            duration_s=duration,
        )

    except FileNotFoundError:
        duration = time.monotonic() - start_time
        return RawResult(
            argv=spec.argv,
            exit_code=127,
            stdout="",
            stderr=f"Command binary not found: {spec.argv[0]}",
            status="unavailable",
            duration_s=duration,
        )
    except PermissionError:
        duration = time.monotonic() - start_time
        return RawResult(
            argv=spec.argv,
            exit_code=126,
            stdout="",
            stderr=f"Permission denied executing: {spec.argv[0]}",
            status="permission_denied",
            duration_s=duration,
        )
    except Exception as exc:
        duration = time.monotonic() - start_time
        return RawResult(
            argv=spec.argv,
            exit_code=-1,
            stdout="",
            stderr=f"Execution error: {exc}",
            status="error",
            duration_s=duration,
        )


def _map_exit_status(exit_code: int, stderr: str) -> ExecutionStatus:
    """Map non-zero exit codes and stderr messages to ExecutionStatus."""
    lower_err = stderr.lower()
    if exit_code in (127,):
        return "unavailable"
    if exit_code in (126,):
        return "permission_denied"
    # Sudo non-interactive password required or permission denied
    if "password" in lower_err or "permission denied" in lower_err or "not permitted" in lower_err:
        return "permission_denied"
    return "error"


def read_system_file(
    path: str,
    max_bytes: int = 1_048_576,
    *,
    enforce_allowlist: bool = True,
) -> RawResult:
    """Safely read native Linux system file (/proc, /sys, /etc) with size bounds.

    Returns RawResult with status 'ok', 'unavailable', or 'permission_denied'.
    """
    clean_path = path.strip().replace("\\", "/")
    if enforce_allowlist and not is_allowlisted_file(clean_path):
        return RawResult(
            argv=("read_file", clean_path),
            exit_code=1,
            stdout="",
            stderr=f"File path '{clean_path}' is not permitted by allow-list",
            status="permission_denied",
        )

    try:
        with open(clean_path, "rb") as f:
            raw_bytes = f.read(max_bytes + 1)
        truncated = len(raw_bytes) > max_bytes
        content_bytes = raw_bytes[:max_bytes]
        content = content_bytes.decode("utf-8", errors="replace")

        # Normalize CRLF to LF
        content = content.replace("\r\n", "\n")

        status: ExecutionStatus = "ok"
        stderr = "Output truncated to max_bytes" if truncated else ""

        return RawResult(
            argv=("read_file", clean_path),
            exit_code=0,
            stdout=content,
            stderr=stderr,
            status=status,
        )

    except FileNotFoundError:
        return RawResult(
            argv=("read_file", clean_path),
            exit_code=1,
            stdout="",
            stderr=f"System file not found: {clean_path}",
            status="unavailable",
        )
    except PermissionError:
        return RawResult(
            argv=("read_file", clean_path),
            exit_code=1,
            stdout="",
            stderr=f"Permission denied reading: {clean_path}",
            status="permission_denied",
        )
    except Exception as exc:
        return RawResult(
            argv=("read_file", clean_path),
            exit_code=1,
            stdout="",
            stderr=f"Error reading file: {exc}",
            status="error",
        )
