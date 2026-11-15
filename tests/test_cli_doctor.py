"""Tests for hwq doctor CLI command (SRS 4.1, FR-CLI-3, FR-PRIV-2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from hwq.cli import app

runner = CliRunner()


def test_doctor_print_sudoers() -> None:
    res = runner.invoke(app, ["doctor", "--print-sudoers"])
    assert res.exit_code == 0
    assert "ALL=(root) NOPASSWD:" in res.output
    assert "dmidecode -t memory" in res.output


def test_doctor_diagnostics_replay() -> None:
    res = runner.invoke(app, ["doctor", "--fixture", "synthetic-8gb-1of2"])
    assert res.exit_code == 0
    assert "hwq Doctor" in res.output
    assert "1. Execution Backend" in res.output
    assert "2. System Tools (Trusted Paths)" in res.output
    assert "3. Privilege & Sudo Status" in res.output
    assert "4. Local LLM Service (Ollama)" in res.output
    assert "synthetic-8gb-1of2" in res.output


def test_doctor_ollama_reachable_mock() -> None:
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"models": [{"name": "llama3:latest"}, {"name": "mistral"}]}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = runner.invoke(app, ["doctor", "--fixture", "synthetic-8gb-1of2"])
        assert res.exit_code == 0
        assert "Reachable" in res.output
        assert "llama3:latest" in res.output


def test_doctor_ollama_unreachable_mock() -> None:
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        res = runner.invoke(app, ["doctor", "--fixture", "synthetic-8gb-1of2"])
        assert res.exit_code == 0
        assert "Unreachable" in res.output
        assert "ollama serve" in res.output
