"""Tests for the golden evaluation harness (SRS Section 6, M7)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from hwq.cli import app
from hwq.eval import EvalCase, run_eval_case, run_eval_suite
from hwq.exec.backend import load_fixture_backend
from hwq.llm.scripted import ScriptedClient

runner = CliRunner()


def test_golden_eval_suite_all_pass() -> None:
    """Golden evaluation suite (AT-1..AT-10) achieves 100% pass rate with scripted client."""
    report = run_eval_suite()
    assert report.total_count == 10
    if not report.all_passed:
        failed = [f"{r.case.id}: {r.failure_reasons}" for r in report.results if not r.passed]
        raise AssertionError(f"Golden eval failures: {failed}")
    assert report.passed_count == 10
    assert report.all_passed is True


def test_cli_eval_table_output() -> None:
    """hwq eval CLI prints evaluation table and reports success."""
    res = runner.invoke(app, ["eval"])
    assert res.exit_code == 0
    assert "hwq Golden Evaluation Suite" in res.output
    assert "Evaluation Succeeded: 10/10 cases passed" in res.output
    assert "AT-1" in res.output
    assert "AT-10" in res.output


def test_cli_eval_json_output() -> None:
    """hwq eval --json outputs valid JSON summary."""
    res = runner.invoke(app, ["eval", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["all_passed"] is True
    assert data["passed_count"] == 10
    assert len(data["results"]) == 10


def test_eval_detects_failure() -> None:
    """EvalCase catches phrase and tool mismatches correctly."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    llm = ScriptedClient()

    case = EvalCase(
        id="TEST-FAIL",
        name="Impossible requirement",
        query="What CPU do I have?",
        fixture="synthetic-8gb-1of2",
        expected_tools=["get_cpu_info"],
        required_phrases=["Quantum Supercomputer 9000"],
    )

    result = run_eval_case(case, backend, llm)
    assert result.passed is False
    assert any("Quantum Supercomputer 9000" in r for r in result.failure_reasons)
