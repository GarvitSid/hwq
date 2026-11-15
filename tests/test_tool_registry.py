"""Tests for ToolRegistry and LLM argument validation (SRS 4.2, FR-TOOL-2..4)."""

from __future__ import annotations

from hwq.exec.backend import load_fixture_backend
from hwq.facts import CpuFact
from hwq.tools.registry import ToolRegistry


def test_tool_registry_definitions() -> None:
    registry = ToolRegistry()
    defs = registry.get_tool_definitions()
    assert len(defs) == 6
    names = [d["function"]["name"] for d in defs]
    assert "get_cpu_info" in names
    assert "get_memory_summary" in names
    assert "get_storage_devices" in names


def test_tool_registry_valid_dict_args() -> None:
    registry = ToolRegistry()
    valid, args, err = registry.validate_tool_call("get_cpu_info", {})
    assert valid is True
    assert args == {}
    assert err is None


def test_tool_registry_valid_json_string_args() -> None:
    """Tolerate arguments passed as JSON string (FR-TOOL-3)."""
    registry = ToolRegistry()
    valid, args, err = registry.validate_tool_call("get_cpu_info", "{}")
    assert valid is True
    assert args == {}
    assert err is None


def test_tool_registry_unknown_tool() -> None:
    """Reject unknown tool and list available tools (FR-TOOL-3)."""
    registry = ToolRegistry()
    valid, args, err = registry.validate_tool_call("run_shell_cmd", {})
    assert valid is False
    assert err is not None
    assert "Unknown tool 'run_shell_cmd'" in err
    assert "get_cpu_info" in err


def test_tool_registry_extra_arguments() -> None:
    """Reject extra arguments (FR-TOOL-3)."""
    registry = ToolRegistry()
    valid, args, err = registry.validate_tool_call("get_cpu_info", {"extra_param": 123})
    assert valid is False
    assert err is not None
    assert "does not accept extra arguments" in err
    assert "extra_param" in err


def test_tool_registry_malformed_json_string() -> None:
    registry = ToolRegistry()
    valid, args, err = registry.validate_tool_call("get_cpu_info", "not valid json")
    assert valid is False
    assert err is not None
    assert "Failed to parse string arguments" in err


def test_tool_registry_non_dict_json() -> None:
    registry = ToolRegistry()
    valid, args, err = registry.validate_tool_call("get_cpu_info", "[1, 2, 3]")
    assert valid is False
    assert err is not None
    assert "must be a JSON object" in err


def test_tool_registry_execute_tool() -> None:
    registry = ToolRegistry()
    backend = load_fixture_backend("synthetic-8gb-1of2")
    env = registry.execute_tool("get_cpu_info", {}, backend)
    assert env.status == "ok"
    assert isinstance(env.data, CpuFact)
