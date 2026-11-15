"""Session management and FactStore caching with TTL expiration (SRS 4.8, FR-CTX-1, FR-CTX-2)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from hwq.facts import (
    CpuFact,
    FactEnvelope,
    GpuFact,
    MemorySummaryFact,
    MemoryTopologyFact,
    StorageFact,
    SystemOverviewFact,
)

VOLATILE_TOOLS: set[str] = {"get_memory_summary"}
VOLATILE_TTL_SECONDS: float = 5.0


@dataclass
class _FactEntry:
    envelope: FactEnvelope[Any]
    inserted_at: float = field(default_factory=time.monotonic)


class FactStore:
    """Session cache retaining hardware facts with TTL awareness (FR-CTX-1)."""

    def __init__(self, volatile_ttl_s: float = VOLATILE_TTL_SECONDS) -> None:
        self.volatile_ttl_s = volatile_ttl_s
        self._entries: dict[str, _FactEntry] = {}

    def put(self, envelope: FactEnvelope[Any]) -> None:
        """Store or update the latest envelope for a tool."""
        self._entries[envelope.tool] = _FactEntry(
            envelope=envelope,
            inserted_at=time.monotonic(),
        )

    def get(self, tool_name: str, check_ttl: bool = True) -> FactEnvelope[Any] | None:
        """Retrieve the latest envelope for a tool if not expired."""
        entry = self._entries.get(tool_name)
        if entry is None:
            return None

        # Check TTL for volatile tools (FR-CTX-1: volatile meminfo expires after 5s)
        if check_ttl and tool_name in VOLATILE_TOOLS:
            elapsed = time.monotonic() - entry.inserted_at
            if elapsed > self.volatile_ttl_s:
                return None

        return entry.envelope

    def has(self, tool_name: str) -> bool:
        """Return True if a fresh fact exists for tool_name."""
        return self.get(tool_name) is not None

    def all_envelopes(self, include_expired: bool = True) -> list[FactEnvelope[Any]]:
        """Return all valid envelopes (by default including volatile facts gathered in session)."""
        envs: list[FactEnvelope[Any]] = []
        for name in list(self._entries.keys()):
            env = self.get(name, check_ttl=not include_expired)
            if env is not None:
                envs.append(env)
        return envs

    def get_index(self) -> list[dict[str, Any]]:
        """Return compact index of active facts for LLM context (FR-CTX-2)."""
        index: list[dict[str, Any]] = []
        now = time.monotonic()
        for name in list(self._entries.keys()):
            env = self.get(name)
            if env is None:
                continue
            entry = self._entries[name]
            age = round(now - entry.inserted_at, 1)
            index.append({
                "tool": name,
                "status": env.status,
                "confidence": env.confidence,
                "age_s": age,
                "summary": self._summarize_data(env),
            })
        return index

    def _summarize_data(self, env: FactEnvelope[Any]) -> str:
        data = env.data
        if isinstance(data, CpuFact):
            cores = data.cores or "?"
            arch = data.architecture or "?"
            return f"CPU: {data.model_name or 'Unknown'} ({cores} cores, {arch})"
        if isinstance(data, MemorySummaryFact):
            tot = data.total_bytes // (1024**2)
            free = data.free_bytes // (1024**2)
            return f"RAM: Total={tot} MiB, Free={free} MiB"
        if isinstance(data, MemoryTopologyFact):
            inst = data.installed_bytes // (1024**3)
            return f"Topology: {data.slots_used} of {data.slots_total} slots, Installed={inst} GiB"
        if isinstance(data, StorageFact):
            d_names = [d.name for d in data.devices]
            return f"Storage: {len(data.devices)} device(s) ({', '.join(d_names)})"
        if isinstance(data, GpuFact):
            g_names = [d.device_name for d in data.devices]
            return f"GPU: {len(data.devices)} device(s) ({', '.join(g_names)})"
        if isinstance(data, SystemOverviewFact):
            prod = data.product_name or data.sys_vendor or "Unknown"
            os_name = data.os_pretty_name or "Linux"
            return f"System: {prod} (OS: {os_name})"
        return f"Status: {env.status}"


class Session:
    """Manages chat messages, fact cache, and session lifecycle."""

    def __init__(
        self,
        session_id: str | None = None,
        fact_store: FactStore | None = None,
    ) -> None:
        self.session_id: str = session_id or str(uuid.uuid4())
        self.fact_store: FactStore = fact_store or FactStore()
        self.messages: list[dict[str, Any]] = []

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(
        self,
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def add_tool_result(self, tool_name: str, result_content: str) -> None:
        self.messages.append({
            "role": "tool",
            "name": tool_name,
            "content": result_content,
        })
