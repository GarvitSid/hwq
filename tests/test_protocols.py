"""Tests for SystemBackend and LLMClient protocols."""

from typing import Any

from hwq.models import CommandSpec, LLMReply, RawResult
from hwq.protocols import LLMClient, SystemBackend


class DummyBackend:
    def run(self, spec: CommandSpec) -> RawResult:
        return RawResult(
            argv=spec.argv,
            exit_code=0,
            stdout="dummy output",
            stderr="",
            status="ok",
        )

    def read_text(self, path: str) -> RawResult:
        return RawResult(
            argv=("read_text", path),
            exit_code=0,
            stdout="dummy content",
            stderr="",
            status="ok",
        )


class IncompleteBackend:
    def run(self, spec: CommandSpec) -> RawResult:
        return RawResult(
            argv=spec.argv,
            exit_code=0,
            stdout="",
            stderr="",
            status="ok",
        )


class DummyLLM:
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> LLMReply:
        return LLMReply(content="Hello world", tool_calls=[])


def test_system_backend_protocol() -> None:
    """DummyBackend conforms to SystemBackend protocol."""
    backend = DummyBackend()
    assert isinstance(backend, SystemBackend)

    spec = CommandSpec(argv=("echo", "test"))
    result = backend.run(spec)
    assert result.status == "ok"
    assert result.stdout == "dummy output"

    file_result = backend.read_text("/proc/cpuinfo")
    assert file_result.status == "ok"


def test_incomplete_backend_protocol() -> None:
    """IncompleteBackend lacks read_text and fails isinstance."""
    incomplete = IncompleteBackend()
    assert not isinstance(incomplete, SystemBackend)


def test_llm_client_protocol() -> None:
    """DummyLLM conforms to LLMClient protocol."""
    client = DummyLLM()
    assert isinstance(client, LLMClient)

    reply = client.chat(messages=[{"role": "user", "content": "hi"}], tools=[], options={})
    assert reply.content == "Hello world"
    assert reply.tool_calls == []


def test_command_spec_immutable() -> None:
    """CommandSpec argv is converted to an immutable tuple."""
    spec = CommandSpec(argv=["echo", "1"])  # type: ignore[arg-type]
    assert isinstance(spec.argv, tuple)
    assert spec.argv == ("echo", "1")
