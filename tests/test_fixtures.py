"""Tests validating all 7 synthetic fixtures and fixture discovery (FR-BE-1, FR-BE-5)."""

import json

from hwq.exec.backend import discover_fixtures, load_fixture_backend
from hwq.models import CommandSpec

REQUIRED_SYNTHETIC_FIXTURES = {
    "synthetic-8gb-1of2",
    "soldered-8gb-no-free-slots",
    "nvme-plus-sata",
    "vm-no-dmi",
    "no-sudo",
    "nvidia-discrete",
    "igpu-amd",
}


def test_fixture_discovery_finds_all_required() -> None:
    """discover_fixtures finds all 7 required synthetic fixtures."""
    fixtures = discover_fixtures()
    for name in REQUIRED_SYNTHETIC_FIXTURES:
        assert name in fixtures, f"Required fixture '{name}' not found by discover_fixtures"
        fixture_dir = fixtures[name]
        assert fixture_dir.is_dir()
        assert (fixture_dir / "index.json").is_file()


def test_fixtures_schema_and_synthetic_flag() -> None:
    """All 7 synthetic fixtures must have schema=1 and synthetic=True."""
    fixtures = discover_fixtures()
    for name in REQUIRED_SYNTHETIC_FIXTURES:
        fixture_dir = fixtures[name]
        index_file = fixture_dir / "index.json"
        data = json.loads(index_file.read_text(encoding="utf-8"))

        assert data.get("schema") == 1, f"Fixture {name} has invalid schema: {data.get('schema')}"
        assert data.get("synthetic") is True, f"Fixture {name} must have synthetic=True"
        assert data.get("name") == name, f"Fixture name mismatch in index: {data.get('name')}"

        entries = data.get("entries", {})
        assert len(entries) > 0, f"Fixture {name} has empty entries"


def test_fixture_files_exist_and_use_lf() -> None:
    """All files referenced in fixture entries must exist, be non-empty, and use LF endings."""
    fixtures = discover_fixtures()
    for name in REQUIRED_SYNTHETIC_FIXTURES:
        fixture_dir = fixtures[name]
        index_file = fixture_dir / "index.json"
        data = json.loads(index_file.read_text(encoding="utf-8"))

        for key, entry in data.get("entries", {}).items():
            rel_path = entry.get("file")
            assert rel_path, f"Entry {key} in fixture {name} missing 'file' attribute"
            target_path = fixture_dir / rel_path
            assert target_path.is_file(), (
                f"Referenced file '{rel_path}' for key '{key}' does not exist in fixture {name}"
            )

            raw_bytes = target_path.read_bytes()
            assert len(raw_bytes) > 0, f"File {rel_path} in fixture {name} is empty"
            assert b"\r\n" not in raw_bytes, (
                f"File {rel_path} in fixture {name} contains CRLF line endings"
            )


def test_replay_each_synthetic_fixture() -> None:
    """Each of the 7 synthetic fixtures can be loaded and queried via ReplayBackend."""
    for name in REQUIRED_SYNTHETIC_FIXTURES:
        backend = load_fixture_backend(name)
        assert backend.name == name
        assert backend.synthetic is True

        # Query lscpu or lsblk or meminfo depending on fixture
        if "cmd:lscpu -J" in backend.entries:
            res = backend.run(CommandSpec(argv=("lscpu", "-J")))
            assert res.status == "ok"
            assert res.stdout != ""

        if "file:/proc/meminfo" in backend.entries:
            res = backend.read_text("/proc/meminfo")
            assert res.status == "ok"
            assert "MemTotal" in res.stdout


def test_no_sudo_fixture_behavior() -> None:
    """Fixture no-sudo specifically reports permission_denied for dmidecode."""
    backend = load_fixture_backend("no-sudo")
    spec = CommandSpec(argv=("dmidecode", "-t", "memory"), privileged=True)
    res = backend.run(spec)
    assert res.status == "permission_denied"
    assert "password" in res.stderr.lower()
