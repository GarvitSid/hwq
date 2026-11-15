"""Tests for hwq CLI."""

from typer.testing import CliRunner

from hwq import __version__
from hwq.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    """hwq --help exits with 0 and prints usage and subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "hwq [OPTIONS] COMMAND [ARGS]..." in result.stdout or "Usage:" in result.stdout
    assert "facts" in result.stdout
    assert "doctor" in result.stdout
    assert "ask" in result.stdout
    assert "snapshot" in result.stdout


def test_cli_version() -> None:
    """hwq --version displays package version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_cli_no_args() -> None:
    """Running hwq without arguments prints banner in M0 scaffold."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "hwq" in result.stdout


def test_cli_invalid_backend() -> None:
    """hwq --backend invalid exits with code 2."""
    result = runner.invoke(app, ["--backend", "bogus"])
    assert result.exit_code == 2
    assert "Invalid backend" in result.stdout


def test_cli_invalid_llm() -> None:
    """hwq --llm invalid exits with code 2."""
    result = runner.invoke(app, ["--llm", "bogus"])
    assert result.exit_code == 2
    assert "Invalid LLM client" in result.stdout


def test_cli_doctor_print_sudoers() -> None:
    """hwq doctor --print-sudoers prints the pinned dmidecode rule."""
    result = runner.invoke(app, ["doctor", "--print-sudoers"])
    assert result.exit_code == 0
    assert "dmidecode -t memory" in result.stdout
