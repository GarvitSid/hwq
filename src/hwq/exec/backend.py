"""System backends: Linux, Replay, and Recording adapters (SRS 2, 3, 4.5).

All modules in hwq.exec must remain stdlib-only.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Final

from hwq.exec.allowlist import list_allowlisted_commands, list_allowlisted_files
from hwq.exec.privilege import build_privileged_cmd
from hwq.exec.runner import read_system_file, run_command
from hwq.models import CommandSpec, ExecutionStatus, RawResult
from hwq.protocols import SystemBackend

# Redaction patterns for sensitive hardware identifiers (FR-PRIV-4, FR-BE-3)
REDACT_SERIAL_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?i)(serial\s*(?:number)?\s*[:=]\s*)([^\r\n]+)"
)
REDACT_ASSET_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?i)(asset\s*tag\s*[:=]\s*)([^\r\n]+)"
)
REDACT_UUID_REGEX: Final[re.Pattern[str]] = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def canonical_cmd_key(spec: CommandSpec) -> str:
    """Generate canonical fixture key for a CommandSpec (FR-BE-1).

    Strips any leading sudo -n and strips directory paths from binary names.
    Example: ('/usr/bin/sudo', '-n', '/usr/sbin/dmidecode', '-t', 'memory')
             -> 'cmd:dmidecode -t memory'
    """
    argv = list(spec.argv)
    # Strip sudo prefix if present
    if len(argv) >= 2 and os.path.basename(argv[0]) == "sudo" and argv[1] == "-n":
        argv = argv[2:]

    if not argv:
        raise ValueError("Cannot generate canonical key for empty argv")

    base_binary = os.path.basename(argv[0])
    normalized_argv = [base_binary, *argv[1:]]
    return f"cmd:{' '.join(normalized_argv)}"


def canonical_file_key(path: str) -> str:
    """Generate canonical fixture key for a file path (FR-BE-1).

    Normalizes Windows backslashes to forward slashes.
    Example: '/proc/meminfo' -> 'file:/proc/meminfo'
    """
    clean_path = path.strip().replace("\\", "/")
    if not clean_path.startswith("/"):
        clean_path = f"/{clean_path}"
    return f"file:{clean_path}"


def redact_hardware_text(text: str) -> str:
    """Redact serial numbers, UUIDs, and asset tags from captured text (FR-PRIV-4)."""
    text = REDACT_SERIAL_REGEX.sub(r"\1[REDACTED]", text)
    text = REDACT_ASSET_REGEX.sub(r"\1[REDACTED]", text)
    text = REDACT_UUID_REGEX.sub("[REDACTED-UUID]", text)
    return text


class LinuxBackend:
    """Live Linux system execution backend using runner and privilege wrapper."""

    def run(self, spec: CommandSpec) -> RawResult:
        """Run an allow-listed CommandSpec, elevating via sudo -n if privileged."""
        target_spec = spec
        if spec.privileged:
            target_spec = build_privileged_cmd(spec)
        return run_command(target_spec)

    def read_text(self, path: str) -> RawResult:
        """Read a text file from native Linux system (/proc, /sys, /etc)."""
        return read_system_file(path)


class ReplayBackend:
    """Offline playback backend that replays raw outputs from a fixture folder (FR-BE-2)."""

    def __init__(self, fixture_dir: Path | str) -> None:
        self.fixture_dir = Path(fixture_dir).resolve()
        self.index_file = self.fixture_dir / "index.json"
        if not self.index_file.is_file():
            raise FileNotFoundError(f"Fixture index not found: {self.index_file}")

        index_raw = self.index_file.read_text(encoding="utf-8")
        self.index: dict[str, Any] = json.loads(index_raw)

        schema_version = self.index.get("schema")
        if schema_version != 1:
            raise ValueError(f"Unsupported fixture schema version: {schema_version}. Expected 1.")

        self.name: str = self.index.get("name", self.fixture_dir.name)
        self.synthetic: bool = bool(self.index.get("synthetic", False))
        self.entries: dict[str, dict[str, Any]] = self.index.get("entries", {})
        self._injected_failures: dict[str, tuple[ExecutionStatus, str]] = {}

    def inject_failure(
        self,
        canonical_key: str,
        status: ExecutionStatus,
        stderr: str = "Injected test failure",
    ) -> None:
        """Inject failure status (timeout, permission_denied, error) for test scenarios."""
        self._injected_failures[canonical_key] = (status, stderr)

    def clear_injected_failures(self) -> None:
        """Clear all injected failure overrides."""
        self._injected_failures.clear()

    def run(self, spec: CommandSpec) -> RawResult:
        """Replay recorded raw command result from fixture."""
        key = canonical_cmd_key(spec)
        return self._lookup_entry(key, spec.argv)

    def read_text(self, path: str) -> RawResult:
        """Replay recorded raw file content from fixture."""
        key = canonical_file_key(path)
        return self._lookup_entry(key, ("read_file", path))

    def _lookup_entry(self, key: str, argv: tuple[str, ...]) -> RawResult:
        # Check injected failures first
        if key in self._injected_failures:
            injected_status, injected_stderr = self._injected_failures[key]
            return RawResult(
                argv=argv,
                exit_code=-1 if injected_status == "timeout" else 1,
                stdout="",
                stderr=injected_stderr,
                status=injected_status,
            )

        entry = self.entries.get(key)
        if entry is None:
            return RawResult(
                argv=argv,
                exit_code=127,
                stdout="",
                stderr=f"Key not recorded in fixture: {key}",
                status="unavailable",
            )

        status: ExecutionStatus = entry.get("status", "ok")
        exit_code: int = entry.get("exit_code", 0 if status == "ok" else 1)
        rel_file = entry.get("file")

        content = ""
        stderr = entry.get("stderr", "")

        if rel_file:
            target_file = self.fixture_dir / rel_file
            if target_file.is_file():
                raw = target_file.read_bytes().decode("utf-8", errors="replace")
                # Normalize CRLF to LF (FR-BE-2)
                content = raw.replace("\r\n", "\n")
            else:
                stderr = f"Fixture file missing on disk: {rel_file}"
                status = "error"
                exit_code = 1

        stdout = content if status == "ok" else ""
        if status != "ok" and not stderr:
            stderr = content

        return RawResult(
            argv=argv,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            status=status,
        )


class RecordingBackend:
    """Decorator backend that records live system outputs into a fixture folder (FR-BE-3)."""

    def __init__(
        self,
        backend: SystemBackend,
        out_dir: Path | str,
        fixture_name: str,
        *,
        synthetic: bool = False,
    ) -> None:
        self.backend = backend
        self.out_dir = Path(out_dir).resolve()
        self.fixture_name = fixture_name
        self.synthetic = synthetic
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.entries: dict[str, dict[str, Any]] = {}

    def run(self, spec: CommandSpec) -> RawResult:
        """Run command on underlying backend, redact outputs, and save to fixture."""
        result = self.backend.run(spec)
        key = canonical_cmd_key(spec)
        self._record_result(key, result, is_cmd=True)
        return result

    def read_text(self, path: str) -> RawResult:
        """Read system file on underlying backend, redact outputs, and save to fixture."""
        result = self.backend.read_text(path)
        key = canonical_file_key(path)
        self._record_result(key, result, is_cmd=False)
        return result

    def _record_result(self, key: str, result: RawResult, is_cmd: bool) -> None:
        file_name = self._make_filename(key, is_cmd)
        target_path = self.out_dir / file_name

        payload = result.stdout if result.status == "ok" else result.stderr
        clean_payload = redact_hardware_text(payload).replace("\r\n", "\n")

        target_path.write_bytes(clean_payload.encode("utf-8"))

        entry: dict[str, Any] = {
            "file": file_name,
            "status": result.status,
            "exit_code": result.exit_code,
        }
        if result.status != "ok":
            entry["stderr"] = redact_hardware_text(result.stderr)
        self.entries[key] = entry
        self.save_index()

    def _make_filename(self, key: str, is_cmd: bool) -> str:
        # Generate clean descriptive filename from key
        suffix = ".json" if "-J" in key else ".txt"
        base = key.replace("cmd:", "").replace("file:", "").replace("/", "_").strip("_")
        clean_base = re.sub(r"[^a-zA-Z0-9_-]+", "_", base)[:50].strip("_")
        return f"{clean_base}{suffix}"

    def save_index(self) -> None:
        """Write index.json to target fixture directory."""
        index_data = {
            "schema": 1,
            "schema_version": 1,
            "name": self.fixture_name,
            "synthetic": self.synthetic,
            "entries": self.entries,
        }
        index_path = self.out_dir / "index.json"
        index_path.write_text(json.dumps(index_data, indent=2) + "\n", encoding="utf-8")


def discover_fixtures(search_dirs: list[Path] | None = None) -> dict[str, Path]:
    """Discover fixture folders by finding `index.json` files (FR-BE-5).

    Returns mapping of fixture name -> directory Path.
    """
    dirs = search_dirs
    if dirs is None:
        candidate_dirs: list[Path] = []
        if "HWQ_FIXTURES_DIR" in os.environ:
            candidate_dirs.append(Path(os.environ["HWQ_FIXTURES_DIR"]))

        # 1. Check current working directory or repo root (development / test runner)
        cwd = Path.cwd()
        candidate_dirs.append(cwd / "tests" / "fixtures")
        candidate_dirs.append(cwd / "fixtures")

        root_dir = Path(__file__).resolve().parent.parent.parent.parent
        candidate_dirs.append(root_dir / "tests" / "fixtures")

        # 2. Check packaged fixtures (site-packages/hwq/fixtures or src/hwq/fixtures)
        pkg_dir = Path(__file__).resolve().parent.parent / "fixtures"
        candidate_dirs.append(pkg_dir)

        dirs = candidate_dirs

    discovered: dict[str, Path] = {}
    for base in dirs:
        if not base.is_dir():
            continue
        for index_path in base.glob("*/index.json"):
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                if data.get("schema") == 1 or data.get("schema_version") == 1:
                    name = data.get("name", index_path.parent.name)
                    if name not in discovered:
                        discovered[name] = index_path.parent
            except Exception:
                continue

    return discovered


def load_fixture_backend(fixture_name_or_path: str | Path) -> ReplayBackend:
    """Resolve a fixture name or path to an instantiated ReplayBackend."""
    path_candidate = Path(fixture_name_or_path)
    if path_candidate.is_dir() and (path_candidate / "index.json").is_file():
        return ReplayBackend(path_candidate)

    # Check relative to cwd
    cwd_candidate = Path.cwd() / "tests" / "fixtures" / fixture_name_or_path
    if cwd_candidate.is_dir() and (cwd_candidate / "index.json").is_file():
        return ReplayBackend(cwd_candidate)

    # Check relative to package fixtures
    pkg_candidate = Path(__file__).resolve().parent.parent / "fixtures" / fixture_name_or_path
    if pkg_candidate.is_dir() and (pkg_candidate / "index.json").is_file():
        return ReplayBackend(pkg_candidate)

    fixtures = discover_fixtures()
    str_name = str(fixture_name_or_path)
    if str_name in fixtures:
        return ReplayBackend(fixtures[str_name])

    raise FileNotFoundError(
        f"Fixture '{fixture_name_or_path}' not found among available fixtures: "
        f"{sorted(fixtures.keys())}"
    )


def record_all_allowlisted(recording_backend: RecordingBackend) -> None:
    """Execute and record every allow-listed command and native system file."""
    for spec in list_allowlisted_commands():
        recording_backend.run(spec)
    for path in list_allowlisted_files():
        recording_backend.read_text(path)
