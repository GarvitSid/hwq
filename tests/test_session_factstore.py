"""Tests for Session and FactStore caching with TTL (SRS 4.8, FR-CTX-1, FR-CTX-2)."""

from __future__ import annotations

import time

from hwq.facts import CpuFact, FactEnvelope, MemorySummaryFact
from hwq.session import FactStore, Session


def test_fact_store_static_retention() -> None:
    store = FactStore()
    cpu_env = FactEnvelope[CpuFact](
        tool="get_cpu_info",
        status="ok",
        data=CpuFact(model_name="Test CPU", cores=4),
    )
    store.put(cpu_env)

    assert store.has("get_cpu_info") is True
    retrieved = store.get("get_cpu_info")
    assert retrieved is not None
    assert retrieved.tool == "get_cpu_info"


def test_fact_store_volatile_expiration() -> None:
    """Volatile facts (/proc/meminfo) expire after TTL (FR-CTX-1)."""
    short_ttl_s = 0.1
    store = FactStore(volatile_ttl_s=short_ttl_s)

    mem_env = FactEnvelope[MemorySummaryFact](
        tool="get_memory_summary",
        status="ok",
        data=MemorySummaryFact(total_bytes=8000000),
    )
    store.put(mem_env)

    # Immediately available
    assert store.has("get_memory_summary") is True

    # After TTL, expired and None
    time.sleep(0.15)
    assert store.has("get_memory_summary") is False
    assert store.get("get_memory_summary") is None


def test_fact_store_get_index() -> None:
    store = FactStore()
    cpu_env = FactEnvelope[CpuFact](
        tool="get_cpu_info",
        status="ok",
        data=CpuFact(model_name="Test CPU", cores=8, architecture="x86_64"),
    )
    store.put(cpu_env)

    index = store.get_index()
    assert len(index) == 1
    assert index[0]["tool"] == "get_cpu_info"
    assert index[0]["status"] == "ok"
    assert "age_s" in index[0]
    assert "CPU: Test CPU" in index[0]["summary"]


def test_session_message_history() -> None:
    session = Session()
    session.add_user_message("What is my RAM?")
    session.add_assistant_message(
        content=None,
        tool_calls=[{"function": {"name": "get_memory_summary", "arguments": {}}}],
    )
    session.add_tool_result("get_memory_summary", '{"total_bytes": 16000000}')
    session.add_assistant_message("You have 16 GB of RAM.")

    assert len(session.messages) == 4
    assert session.messages[0]["role"] == "user"
    assert session.messages[1]["role"] == "assistant"
    assert session.messages[2]["role"] == "tool"
    assert session.messages[3]["role"] == "assistant"
