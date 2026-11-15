"""Tests for hwq facts CLI command across categories and fixtures (SRS 4.1, FR-CLI-2)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from hwq.cli import app

runner = CliRunner()

FIXTURE_NAMES = [
    "synthetic-8gb-1of2",
    "soldered-8gb-no-free-slots",
    "nvme-plus-sata",
    "vm-no-dmi",
    "no-sudo",
    "nvidia-discrete",
    "igpu-amd",
]


def test_facts_invalid_category() -> None:
    res = runner.invoke(app, ["facts", "nonexistent"])
    assert res.exit_code == 2
    assert "Invalid category" in res.output


def test_facts_cpu_category() -> None:
    res = runner.invoke(app, ["facts", "cpu", "--fixture", "synthetic-8gb-1of2"])
    assert res.exit_code == 0
    assert "CPU Hardware Facts" in res.output
    assert "x86_64" in res.output


def test_facts_memory_category() -> None:
    res = runner.invoke(app, ["facts", "memory", "--fixture", "synthetic-8gb-1of2"])
    assert res.exit_code == 0
    assert "Memory Usage & Summary" in res.output
    assert "Memory Upgrade Advisor" in res.output
    assert "16 GiB" in res.output
    assert "32 GiB" in res.output


def test_facts_storage_category_at9() -> None:
    """AT-9 Units check: verify storage device formatted correctly in CLI facts."""
    res = runner.invoke(app, ["facts", "storage", "--fixture", "nvme-plus-sata"])
    assert res.exit_code == 0
    assert "Storage Block Devices" in res.output
    assert "nvme0n1" in res.output
    assert "477 GiB (about 512 GB)" in res.output
    assert "932 GiB (about 1 TB)" in res.output


def test_facts_gpu_category_at8() -> None:
    """AT-8 check: verify integrated GPU shared memory note in CLI facts."""
    res = runner.invoke(app, ["facts", "gpu", "--fixture", "igpu-amd"])
    assert res.exit_code == 0
    assert "Graphics & GPU Controllers" in res.output
    assert "shared system memory" in res.output.lower()


def test_facts_system_category() -> None:
    res = runner.invoke(app, ["facts", "system", "--fixture", "synthetic-8gb-1of2"])
    assert res.exit_code == 0
    assert "System Overview" in res.output


def test_facts_json_output() -> None:
    res = runner.invoke(app, ["facts", "all", "--json", "--fixture", "synthetic-8gb-1of2"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert "cpu" in data
    assert "memory_summary" in data
    assert "memory_topology" in data
    assert "memory_upgrade" in data
    assert "storage" in data
    assert "gpu" in data
    assert "system" in data
    assert data["memory_upgrade"]["slots_total"] == 2
    assert data["memory_upgrade"]["per_slot_suggestion_bytes"] == 32 * (1024**3)


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_facts_all_works_on_every_fixture(fixture_name: str) -> None:
    """Acceptance criteria M4: 'hwq facts all works on every fixture'."""
    res = runner.invoke(app, ["facts", "all", "--fixture", fixture_name])
    assert res.exit_code == 0
    assert "CPU Hardware Facts" in res.output
    assert "Memory Usage & Summary" in res.output
    assert "Storage Block Devices" in res.output
    assert "Graphics & GPU Controllers" in res.output
    assert "System Overview" in res.output
