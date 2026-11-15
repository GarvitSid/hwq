"""Tests for degraded modes: no-sudo and missing binaries (SRS 4.4, 4.2, AT-2, AT-7)."""

from __future__ import annotations

from hwq.exec.backend import load_fixture_backend
from hwq.llm.scripted import ScriptedClient
from hwq.orchestrator import Orchestrator
from hwq.session import Session
from hwq.tools.registry import ToolRegistry


def test_at2_no_sudo_degraded_mode_full() -> None:
    """AT-2 on no-sudo: gives usable RAM, states slots unknown, explains fix."""
    backend = load_fixture_backend("no-sudo")
    llm = ScriptedClient()
    orchestrator = Orchestrator(backend=backend, llm=llm)
    session = Session()

    ans = orchestrator.run_turn(session, "How much RAM can I upgrade to?")

    # Gives usable RAM (~8 GB / 7.8 GiB)
    assert any(ram in ans for ram in ("8 GB", "7.8 GiB", "8 GiB", "8192000"))
    # Says max and slots cannot be determined
    assert "cannot be determined" in ans.lower()
    # Explains fix
    assert "hwq doctor --print-sudoers" in ans


def test_at7_missing_binary_lspci() -> None:
    """AT-7 Missing binary (lspci): tool unregistered or marked unavailable, answer says why."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    registry = ToolRegistry()

    # Simulate missing lspci binary
    registry.mark_unavailable(
        "get_gpu_info",
        "Required binary 'lspci' was not found in trusted system paths.",
    )

    # Tool definitions must omit unavailable tool (FR-TOOL-4)
    tool_defs = registry.get_tool_definitions()
    tool_names = [d["function"]["name"] for d in tool_defs]
    assert "get_gpu_info" not in tool_names

    # Check unavailable summary
    unavail = registry.get_unavailable_tools_summary()
    assert any("lspci" in u for u in unavail)

    # Run query through orchestrator
    llm = ScriptedClient()
    orchestrator = Orchestrator(backend=backend, llm=llm, tool_registry=registry)
    session = Session()

    ans = orchestrator.run_turn(session, "What GPU is installed?")
    assert "unavailable" in ans.lower()
    assert "lspci" in ans.lower()
