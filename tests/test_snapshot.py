"""Tests for snapshot acquisition and standalone CLI (FR-BE-4)."""

import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from hwq.cli import app
from hwq.snapshot import main as snapshot_main

runner = CliRunner()


def test_snapshot_module_cli_help() -> None:
    """python -m hwq.snapshot --help exits with 0 and prints usage."""
    cmd = [sys.executable, "-m", "hwq.snapshot", "--help"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "Record read-only Linux hardware outputs" in proc.stdout
    assert "--out" in proc.stdout


def test_snapshot_main_invocation(tmp_path: Path) -> None:
    """snapshot_main executes and produces a valid fixture folder."""
    out_dir = tmp_path / "cli_snapshot"
    exit_code = snapshot_main(["--out", str(out_dir), "--name", "cli-test", "--synthetic"])
    assert exit_code == 0
    assert (out_dir / "index.json").is_file()

    index_data = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
    assert index_data.get("schema") == 1
    assert index_data.get("name") == "cli-test"
    assert index_data.get("synthetic") is True


def test_hwq_cli_snapshot_command(tmp_path: Path) -> None:
    """hwq snapshot --out DIR command runs through Typer CLI."""
    out_dir = tmp_path / "typer_snapshot"
    result = runner.invoke(app, ["snapshot", "--out", str(out_dir)])
    assert result.exit_code == 0
    assert (out_dir / "index.json").is_file()
