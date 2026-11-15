"""Tests for Orchestrator and agent loop (SRS 4.9, AT-4, AT-5)."""

from __future__ import annotations

from hwq.exec.backend import load_fixture_backend
from hwq.llm.scripted import ScriptedClient
from hwq.models import LLMReply
from hwq.orchestrator import Orchestrator
from hwq.prompts import OUT_OF_SCOPE_REFUSAL
from hwq.session import Session


def test_orchestrator_at5_out_of_scope_refusal() -> None:
    """AT-5 'delete my logs' / 'run ls': one-sentence refusal, no tool call."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    llm = ScriptedClient()
    orchestrator = Orchestrator(backend=backend, llm=llm)
    session = Session()

    executed_tools: list[str] = []

    def on_tool(name: str, status: str, conf: str) -> None:
        executed_tools.append(name)

    ans1 = orchestrator.run_turn(session, "delete my logs", on_tool_call=on_tool)
    assert ans1 == OUT_OF_SCOPE_REFUSAL
    assert len(executed_tools) == 0

    ans2 = orchestrator.run_turn(session, "run ls -la /tmp", on_tool_call=on_tool)
    assert ans2 == OUT_OF_SCOPE_REFUSAL
    assert len(executed_tools) == 0


def test_orchestrator_at4_follow_up_pruning() -> None:
    """AT-4 Follow-up 'and the GPU?' after RAM: only the GPU tool runs."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    llm = ScriptedClient()
    orchestrator = Orchestrator(backend=backend, llm=llm)
    session = Session()

    turn1_tools: list[str] = []
    ans1 = orchestrator.run_turn(
        session,
        "How much RAM do I have?",
        on_tool_call=lambda n, s, c: turn1_tools.append(n),
    )
    assert len(ans1) > 0
    assert "get_memory_summary" in turn1_tools
    assert "get_memory_topology" in turn1_tools
    assert "get_gpu_info" not in turn1_tools

    # Turn 2: Follow-up asking about GPU
    turn2_tools: list[str] = []
    ans2 = orchestrator.run_turn(
        session,
        "and the GPU?",
        on_tool_call=lambda n, s, c: turn2_tools.append(n),
    )
    assert len(ans2) > 0
    assert turn2_tools == ["get_gpu_info"]


def test_orchestrator_malformed_argument_recovery() -> None:
    """Orchestrator feeds validation error back to LLM, allowing it to recover."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    llm = ScriptedClient()

    # Queue reply 1: malformed tool call with extra arguments
    llm.queue_reply(
        LLMReply(
            content=None,
            tool_calls=[{"function": {"name": "get_cpu_info", "arguments": {"invalid_arg": 1}}}],
        )
    )
    # Queue reply 2: corrected tool call
    llm.queue_reply(
        LLMReply(
            content=None,
            tool_calls=[{"function": {"name": "get_cpu_info", "arguments": {}}}],
        )
    )
    # Queue reply 3: final answer
    llm.queue_reply(
        LLMReply(
            content="CPU has 8 cores.",
            tool_calls=[],
        )
    )

    orchestrator = Orchestrator(backend=backend, llm=llm)
    session = Session()
    ans = orchestrator.run_turn(session, "What CPU is installed?")
    assert ans == "CPU has 8 cores."


def test_orchestrator_max_rounds_bounding() -> None:
    backend = load_fixture_backend("synthetic-8gb-1of2")
    llm = ScriptedClient()

    # Infinite loop of tool calls
    for _ in range(10):
        llm.queue_reply(
            LLMReply(
                content=None,
                tool_calls=[{"function": {"name": "get_cpu_info", "arguments": {}}}],
            )
        )

    orchestrator = Orchestrator(backend=backend, llm=llm, max_rounds=3)
    session = Session()
    ans = orchestrator.run_turn(session, "Tell me about the CPU")
    assert "maximum tool rounds" in ans.lower()
