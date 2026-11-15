"""Tests for Orchestrator grounding check, retry, and fallback (FR-GRD-1, FR-GRD-2)."""

from __future__ import annotations

from hwq.exec.backend import load_fixture_backend
from hwq.llm.scripted import ScriptedClient
from hwq.models import LLMReply
from hwq.orchestrator import Orchestrator
from hwq.session import Session


def test_orchestrator_grounding_accepts_valid() -> None:
    backend = load_fixture_backend("synthetic-8gb-1of2")
    llm = ScriptedClient()

    # Reply 1: Tool call for CPU
    llm.queue_reply(
        LLMReply(
            content=None,
            tool_calls=[{"function": {"name": "get_cpu_info", "arguments": {}}}],
        )
    )
    # Reply 2: Perfectly grounded answer
    llm.queue_reply(
        LLMReply(
            content="Your CPU has 4 cores and 8 threads.",
            tool_calls=[],
        )
    )

    orchestrator = Orchestrator(backend=backend, llm=llm)
    session = Session()
    ans = orchestrator.run_turn(session, "How many cores does my CPU have?")
    assert ans == "Your CPU has 4 cores and 8 threads."


def test_orchestrator_grounding_rejects_and_recovers_on_retry() -> None:
    """Ungrounded draft is rejected; LLM recovers on 1-retry regeneration (FR-GRD-2)."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    llm = ScriptedClient()

    # Reply 1: Tool call for CPU
    llm.queue_reply(
        LLMReply(
            content=None,
            tool_calls=[{"function": {"name": "get_cpu_info", "arguments": {}}}],
        )
    )
    # Reply 2: Ungrounded answer (hallucinating 16 cores)
    llm.queue_reply(
        LLMReply(
            content="Your CPU has 16 cores and 32 threads.",
            tool_calls=[],
        )
    )
    # Reply 3: Correction after receiving discrepancy feedback
    llm.queue_reply(
        LLMReply(
            content="Correction: Your CPU actually has 4 cores and 8 threads.",
            tool_calls=[],
        )
    )

    orchestrator = Orchestrator(backend=backend, llm=llm)
    session = Session()
    ans = orchestrator.run_turn(session, "How many cores does my CPU have?")

    assert ans == "Correction: Your CPU actually has 4 cores and 8 threads."


def test_orchestrator_grounding_falls_back_to_template_after_failed_retry() -> None:
    """When retry draft also fails grounding, emit deterministic template answer (FR-GRD-2)."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    llm = ScriptedClient()

    # Reply 1: Tool call for CPU
    llm.queue_reply(
        LLMReply(
            content=None,
            tool_calls=[{"function": {"name": "get_cpu_info", "arguments": {}}}],
        )
    )
    # Reply 2: Ungrounded draft
    llm.queue_reply(
        LLMReply(
            content="Your CPU has 64 cores.",
            tool_calls=[],
        )
    )
    # Reply 3: Retry draft still ungrounded
    llm.queue_reply(
        LLMReply(
            content="Still claiming your CPU has 64 cores.",
            tool_calls=[],
        )
    )

    orchestrator = Orchestrator(backend=backend, llm=llm)
    session = Session()
    ans = orchestrator.run_turn(session, "How many cores does my CPU have?")

    # Must fall back to template containing genuine facts
    assert "i5-1135G7" in ans
    assert "4 cores" in ans
    assert "64 cores" not in ans
