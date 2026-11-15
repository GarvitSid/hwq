"""Tests for system backends: LinuxBackend, ReplayBackend, RecordingBackend (SRS 4.5)."""

import json
import sys
from pathlib import Path

import pytest

from hwq.exec.backend import (
    LinuxBackend,
    RecordingBackend,
    ReplayBackend,
    canonical_cmd_key,
    canonical_file_key,
    load_fixture_backend,
    redact_hardware_text,
)
from hwq.models import CommandSpec, RawResult


class MockSystemBackend:
    """Mock backend for round-trip recording and replay verification."""

    def run(self, spec: CommandSpec) -> RawResult:
        if any("lscpu" in a for a in spec.argv):
            return RawResult(
                argv=spec.argv,
                exit_code=0,
                stdout='{"lscpu": [{"field": "CPU(s):", "data": "8"}]}\r\n',
                stderr="",
                status="ok",
            )
        if any("dmidecode" in a for a in spec.argv):
            return RawResult(
                argv=spec.argv,
                exit_code=0,
                stdout="Handle 0x01\n\tSerial Number: SN123456789\n\tAsset Tag: ASSET9876\n",
                stderr="",
                status="ok",
            )
        return RawResult(
            argv=spec.argv,
            exit_code=127,
            stdout="",
            stderr="not found",
            status="unavailable",
        )

    def read_text(self, path: str) -> RawResult:
        if path == "/proc/meminfo":
            return RawResult(
                argv=("read_file", path),
                exit_code=0,
                stdout="MemTotal: 16000000 kB\r\nMemFree: 8000000 kB\r\n",
                stderr="",
                status="ok",
            )
        return RawResult(
            argv=("read_file", path),
            exit_code=1,
            stdout="",
            stderr="missing",
            status="unavailable",
        )


def test_canonical_cmd_key_formatting() -> None:
    """canonical_cmd_key strips sudo -n and directory paths."""
    spec1 = CommandSpec(argv=("/usr/bin/sudo", "-n", "/usr/sbin/dmidecode", "-t", "memory"))
    assert canonical_cmd_key(spec1) == "cmd:dmidecode -t memory"

    spec2 = CommandSpec(argv=("lscpu", "-J"))
    assert canonical_cmd_key(spec2) == "cmd:lscpu -J"

    spec3 = CommandSpec(argv=("/usr/bin/lscpu", "-J"))
    assert canonical_cmd_key(spec3) == "cmd:lscpu -J"


def test_canonical_file_key_formatting() -> None:
    """canonical_file_key normalizes paths to forward slashes."""
    assert canonical_file_key("/proc/meminfo") == "file:/proc/meminfo"
    assert canonical_file_key(r"\proc\meminfo") == "file:/proc/meminfo"


def test_redact_hardware_text() -> None:
    """redact_hardware_text removes serials, UUIDs, and asset tags."""
    raw = (
        "Serial Number: 4C4C4544-004B-4E10-8043-B2C04F343233\n"
        "Asset Tag: ASSET-TAG-001\n"
        "UUID: 12345678-1234-1234-1234-123456789abc\n"
        "Model: Samsung SSD 980\n"
    )
    redacted = redact_hardware_text(raw)
    assert "[REDACTED]" in redacted
    assert "[REDACTED-UUID]" in redacted
    assert "4C4C4544" not in redacted
    assert "ASSET-TAG-001" not in redacted
    assert "12345678-1234-1234-1234-123456789abc" not in redacted
    assert "Model: Samsung SSD 980" in redacted


def test_replay_backend_success() -> None:
    """ReplayBackend replays commands and files from synthetic-8gb-1of2."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    assert backend.synthetic is True

    # Replay command
    spec = CommandSpec(argv=("lscpu", "-J"))
    result = backend.run(spec)
    assert result.status == "ok"
    assert result.exit_code == 0
    assert "GenuineIntel" in result.stdout
    assert "\r\n" not in result.stdout  # CRLF normalized to LF

    # Replay file
    file_result = backend.read_text("/proc/meminfo")
    assert file_result.status == "ok"
    assert "MemTotal" in file_result.stdout
    assert "\r\n" not in file_result.stdout


def test_replay_backend_unknown_key() -> None:
    """ReplayBackend returns unavailable for commands not recorded in fixture."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    spec = CommandSpec(argv=("unknown_tool", "--flag"))
    result = backend.run(spec)
    assert result.status == "unavailable"
    assert result.exit_code == 127
    assert "not recorded in fixture" in result.stderr


def test_replay_backend_injected_failures() -> None:
    """ReplayBackend supports injected failure states for test coverage."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    spec = CommandSpec(argv=("lscpu", "-J"))

    # Normal replay
    assert backend.run(spec).status == "ok"

    # Inject timeout
    backend.inject_failure("cmd:lscpu -J", "timeout", "Execution timed out")
    res_timeout = backend.run(spec)
    assert res_timeout.status == "timeout"
    assert res_timeout.exit_code == -1

    # Inject permission_denied
    backend.inject_failure("cmd:lscpu -J", "permission_denied", "Access denied")
    res_denied = backend.run(spec)
    assert res_denied.status == "permission_denied"

    # Clear injected failures
    backend.clear_injected_failures()
    assert backend.run(spec).status == "ok"


def test_recording_and_replay_roundtrip(tmp_path: Path) -> None:
    """Test full record -> replay round-trip using MockSystemBackend."""
    out_dir = tmp_path / "roundtrip_fixture"
    mock_backend = MockSystemBackend()
    recorder = RecordingBackend(
        backend=mock_backend,
        out_dir=out_dir,
        fixture_name="test-roundtrip",
        synthetic=True,
    )

    # Record command and file
    cmd_spec = CommandSpec(argv=("/usr/bin/lscpu", "-J"))
    dmi_spec = CommandSpec(argv=("/usr/bin/sudo", "-n", "/usr/sbin/dmidecode", "-t", "memory"))
    recorder.run(cmd_spec)
    recorder.run(dmi_spec)
    recorder.read_text("/proc/meminfo")

    # Verify fixture files created on disk
    assert (out_dir / "index.json").is_file()
    index_data = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
    for entry in index_data["entries"].values():
        assert (out_dir / entry["file"]).is_file()

    # Verify redaction took place in recorded file
    dmi_file = index_data["entries"]["cmd:dmidecode -t memory"]["file"]
    dmi_content = (out_dir / dmi_file).read_text(encoding="utf-8")
    assert "SN123456789" not in dmi_content
    assert "ASSET9876" not in dmi_content
    assert "[REDACTED]" in dmi_content

    # Load recorded fixture with ReplayBackend
    replay = ReplayBackend(out_dir)
    assert replay.name == "test-roundtrip"
    assert replay.synthetic is True

    # Replay command
    res1 = replay.run(cmd_spec)
    assert res1.status == "ok"
    assert "CPU(s)" in res1.stdout
    assert "\r\n" not in res1.stdout

    # Replay file
    res2 = replay.read_text("/proc/meminfo")
    assert res2.status == "ok"
    assert "MemTotal" in res2.stdout
    assert "\r\n" not in res2.stdout


@pytest.mark.linux
def test_live_linux_backend_read() -> None:
    """Test LinuxBackend reading /proc/meminfo on real Linux host."""
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux-only test requires real Linux environment")
    backend = LinuxBackend()
    result = backend.read_text("/proc/meminfo")
    assert result.status == "ok"
    assert "MemTotal" in result.stdout
