"""Comprehensive freeze security audit tests for Milestone 8 (SRS Section 5 & 6, M8)."""

from __future__ import annotations

import ast
from pathlib import Path

from hwq.exec.allowlist import ALLOWED_COMMANDS
from hwq.exec.backend import load_fixture_backend
from hwq.grounding import build_ground_truth, validate_numeric_grounding
from hwq.llm.scripted import ScriptedClient
from hwq.models import LLMReply
from hwq.orchestrator import Orchestrator
from hwq.session import Session

SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def test_audit_no_forbidden_primitives_in_src() -> None:
    """Zero occurrences of shell=True, os.system, eval, exec, or pickle across src/."""
    forbidden_calls = {"eval", "exec"}
    forbidden_os_attrs = {"system", "popen"}

    for py_file in SRC_DIR.rglob("*.py"):
        code = py_file.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(py_file))

        for node in ast.walk(tree):
            # Check forbidden function calls: eval(), exec()
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                    raise AssertionError(
                        f"Forbidden call '{node.func.id}' in {py_file}:{node.lineno}"
                    )

                # Check os.system, os.popen
                if isinstance(node.func, ast.Attribute):
                    if (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                        and node.func.attr in forbidden_os_attrs
                    ):
                        raise AssertionError(
                            f"Forbidden 'os.{node.func.attr}' in {py_file}:{node.lineno}"
                        )

                # Check subprocess keyword arguments for shell=True
                for kw in node.keywords:
                    if kw.arg == "shell":
                        if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            raise AssertionError(
                                f"Forbidden 'shell=True' in {py_file}:{node.lineno}"
                            )

            # Check forbidden imports: pickle
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "pickle":
                        raise AssertionError(
                            f"Forbidden import 'pickle' in {py_file}:{node.lineno}"
                        )
            if isinstance(node, ast.ImportFrom):
                if node.module == "pickle":
                    raise AssertionError(f"Forbidden 'from pickle' in {py_file}:{node.lineno}")


def test_audit_privilege_confinement() -> None:
    """Only dmidecode -t memory is privileged; no serials, UUIDs, or asset tags queried."""
    privileged_specs = [spec for spec in ALLOWED_COMMANDS.values() if spec.privileged]
    assert len(privileged_specs) == 1, (
        f"Expected exactly 1 privileged command, got: {privileged_specs}"
    )

    priv = privileged_specs[0]
    assert priv.argv == ("dmidecode", "-t", "memory")

    # Verify no command queries serial numbers, UUIDs, or asset tags
    forbidden_args = {
        "-s",
        "system-serial-number",
        "system-uuid",
        "chassis-asset-tag",
        "baseboard-serial-number",
    }
    for spec in ALLOWED_COMMANDS.values():
        for arg in spec.argv:
            assert arg not in forbidden_args, (
                f"Forbidden privacy-violating argument '{arg}' in {spec}"
            )


def test_audit_live_usb_stdlib_only() -> None:
    """hwq.exec.* and hwq.snapshot carry zero third-party dependencies."""
    third_party_disallowed = {
        "pydantic",
        "typer",
        "rich",
        "requests",
        "urllib3",
        "httpx",
        "yaml",
        "hypothesis",
    }

    dirs_to_check = [
        SRC_DIR / "hwq" / "exec",
        SRC_DIR / "hwq" / "snapshot.py",
    ]

    for item in dirs_to_check:
        files = [item] if item.is_file() else list(item.rglob("*.py"))
        for py_file in files:
            code = py_file.read_text(encoding="utf-8")
            tree = ast.parse(code, filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        assert top not in third_party_disallowed, (
                            f"Live USB boundary violation: '{top}' imported in {py_file}"
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        top = node.module.split(".")[0]
                        assert top not in third_party_disallowed, (
                            f"Live USB boundary violation: '{top}' imported in {py_file}"
                        )


def test_audit_grounding_intercepts_hallucinations() -> None:
    """Orchestrator grounding interceptor strictly prevents ungrounded draft from reaching user."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    llm = ScriptedClient()

    # Reply 1: Tool call
    llm.queue_reply(
        LLMReply(
            content=None,
            tool_calls=[{"function": {"name": "get_cpu_info", "arguments": {}}}],
        )
    )
    # Reply 2: Hallucinated CPU core count (claims 64 cores on a 4-core CPU)
    llm.queue_reply(
        LLMReply(
            content="You have an Intel CPU with 64 cores and 128 threads.",
            tool_calls=[],
        )
    )
    # Reply 3: Second attempt also hallucinates
    llm.queue_reply(
        LLMReply(
            content="Correction: You have an Intel CPU with 32 cores.",
            tool_calls=[],
        )
    )

    orchestrator = Orchestrator(backend=backend, llm=llm)
    session = Session()
    ans = orchestrator.run_turn(session, "How many CPU cores do I have?")

    # Hallucinated 64 cores or 32 cores MUST NOT be returned; fallback template is used
    assert "64 cores" not in ans
    assert "32 cores" not in ans
    # True core count from fact envelope is 4 cores
    assert "4" in ans

    # Ground truth validation on final rendered answer must pass
    gt = build_ground_truth(session.fact_store.all_envelopes())
    grounding = validate_numeric_grounding(ans, gt)
    assert grounding.is_grounded is True
