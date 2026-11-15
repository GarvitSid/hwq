"""System backend and LLM client protocols (SRS Section 3)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from hwq.models import CommandSpec, LLMReply, RawResult


@runtime_checkable
class SystemBackend(Protocol):
    """Abstract system access adapter (LinuxBackend, ReplayBackend, RecordingBackend)."""

    def run(self, spec: CommandSpec) -> RawResult:
        """Execute a command specification and return raw result."""
        ...

    def read_text(self, path: str) -> RawResult:
        """Read a text file from the system (/proc, /sys, /etc) and return raw result."""
        ...


@runtime_checkable
class LLMClient(Protocol):
    """Abstract LLM adapter (OllamaClient, ScriptedClient)."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> LLMReply:
        """Send chat messages and tool definitions to the model and return its response."""
        ...
