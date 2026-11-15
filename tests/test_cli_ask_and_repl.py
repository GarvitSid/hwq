"""Tests for hwq ask and interactive REPL CLI (SRS 4.1, FR-CLI-1, FR-CLI-5, FR-CLI-6, AT-5)."""

from __future__ import annotations

import urllib.error
from unittest.mock import patch

from typer.testing import CliRunner

from hwq.cli import app

runner = CliRunner()


def test_cli_ask_cpu_with_scripted() -> None:
    res = runner.invoke(
        app,
        ["ask", "What CPU do I have?", "--llm", "scripted", "--fixture", "synthetic-8gb-1of2"],
    )
    assert res.exit_code == 0
    assert len(res.output) > 0
    assert "Intel Core i5-1135G7" in res.output or "4 cores" in res.output


def test_cli_ask_show_tools() -> None:
    """--show-tools prints each tool call with status/confidence (FR-CLI-5)."""
    res = runner.invoke(
        app,
        [
            "ask",
            "What CPU do I have?",
            "--llm",
            "scripted",
            "--fixture",
            "synthetic-8gb-1of2",
            "--show-tools",
        ],
    )
    assert res.exit_code == 0
    assert "[Tool] get_cpu_info -> status=ok" in res.output


def test_cli_ask_at5_out_of_scope_refusal() -> None:
    """AT-5 'delete my logs' / 'run ls': one-sentence refusal, no tool call."""
    res = runner.invoke(
        app,
        ["ask", "delete my logs", "--llm", "scripted"],
    )
    assert res.exit_code == 0
    norm_output = " ".join(res.output.split())
    assert "cannot execute commands or modify system state" in norm_output


def test_cli_ask_ollama_unreachable_exits_with_help() -> None:
    """If Ollama is unreachable, print how to fix it and offer hwq facts (FR-LLM-4)."""
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        res = runner.invoke(
            app,
            ["ask", "What CPU do I have?", "--llm", "ollama"],
        )
        assert res.exit_code == 1
        assert "LLM Error:" in res.output
        assert "hwq facts" in res.output


def test_cli_repl_exit() -> None:
    """Interactive REPL starts, reads inputs, and exits on 'exit' (FR-CLI-1)."""
    res = runner.invoke(
        app,
        ["--demo"],
        input="exit\n",
    )
    assert res.exit_code == 0
    assert "hwq" in res.output
    assert "Goodbye!" in res.output


def test_cli_repl_query_and_exit() -> None:
    """Interactive REPL processes query then exits."""
    res = runner.invoke(
        app,
        ["--demo"],
        input="What CPU do I have?\nexit\n",
    )
    assert res.exit_code == 0
    assert "Intel Core i5-1135G7" in res.output or "4 cores" in res.output
    assert "Goodbye!" in res.output
