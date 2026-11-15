"""Tool registry and strict LLM argument validation (SRS 4.2, FR-TOOL-2..4, AT-7)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from hwq.exec.backend import LinuxBackend, ReplayBackend
from hwq.exec.probe import find_binary
from hwq.facts import FactEnvelope
from hwq.protocols import SystemBackend
from hwq.tools import get_all_tools
from hwq.tools.base import Tool

REQUIRED_BINARIES: dict[str, str] = {
    "get_cpu_info": "lscpu",
    "get_gpu_info": "lspci",
    "get_storage_devices": "lsblk",
    "get_memory_topology": "dmidecode",
}


class ToolRegistry:
    """Registry managing available hardware tools, OpenAI schemas, and validation."""

    def __init__(self, tools: Sequence[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._unavailable_tools: dict[str, str] = {}
        tool_list = tools if tools is not None else get_all_tools()
        for t in tool_list:
            self._tools[t.name] = t

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    @property
    def unavailable_tools(self) -> dict[str, str]:
        return dict(self._unavailable_tools)

    def mark_unavailable(self, tool_name: str, reason: str) -> None:
        """Mark a tool as unavailable with an explanatory reason (FR-TOOL-4, AT-7)."""
        self._unavailable_tools[tool_name] = reason

    def probe_availability(self, backend: SystemBackend) -> None:
        """Probe system tools to register only usable tools (FR-TOOL-4, AT-7)."""
        if isinstance(backend, LinuxBackend):
            for tool_name, binary in REQUIRED_BINARIES.items():
                if tool_name in self._tools and find_binary(binary) is None:
                    self.mark_unavailable(
                        tool_name,
                        f"Required binary '{binary}' was not found in trusted system paths.",
                    )
        elif isinstance(backend, ReplayBackend):
            # If fixture explicitly records an entry as unavailable
            for tool_name, binary in REQUIRED_BINARIES.items():
                cmd_key = f"cmd:{binary}"
                # Check if all commands starting with this binary are unavailable
                matching = [k for k in backend.entries if k.startswith(cmd_key)]
                if matching and all(
                    backend.entries[k].get("status") == "unavailable" for k in matching
                ):
                    self.mark_unavailable(
                        tool_name,
                        f"Binary '{binary}' is unavailable on target system.",
                    )

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Generate OpenAI/Ollama tool definition schemas for usable tools only (FR-TOOL-4)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters_schema,
                },
            }
            for t in self._tools.values()
            if t.name not in self._unavailable_tools
        ]

    def get_unavailable_tools_summary(self) -> list[str]:
        """Return descriptions of unavailable tools for LLM context (FR-TOOL-4)."""
        return [
            f"Tool '{name}' is unavailable: {reason}"
            for name, reason in self._unavailable_tools.items()
        ]

    def validate_tool_call(
        self,
        name: str,
        raw_arguments: Any,
    ) -> tuple[bool, dict[str, Any], str | None]:
        """Validate an LLM tool call per FR-TOOL-3.

        Returns:
            (is_valid, validated_args_dict, error_message_or_none)
        """
        if name in self._unavailable_tools:
            return (
                False,
                {},
                f"Error: Tool '{name}' is unavailable: {self._unavailable_tools[name]}",
            )

        tool = self._tools.get(name)
        if tool is None:
            avail = sorted(t for t in self._tools if t not in self._unavailable_tools)
            return (
                False,
                {},
                f"Error: Unknown tool '{name}'. Available tools are: {avail}",
            )

        # Tolerate string-encoded JSON arguments or dicts
        parsed_args: dict[str, Any]
        if isinstance(raw_arguments, str):
            raw_str = raw_arguments.strip()
            if not raw_str:
                parsed_args = {}
            else:
                try:
                    loaded = json.loads(raw_str)
                    if not isinstance(loaded, dict):
                        return (
                            False,
                            {},
                            f"Error: Tool arguments for '{name}' must be a JSON object, got "
                            f"{type(loaded).__name__}.",
                        )
                    parsed_args = loaded
                except Exception as exc:
                    return (
                        False,
                        {},
                        f"Error: Failed to parse string arguments as JSON for '{name}': {exc}",
                    )
        elif isinstance(raw_arguments, dict):
            parsed_args = raw_arguments
        elif raw_arguments is None:
            parsed_args = {}
        else:
            return (
                False,
                {},
                f"Error: Arguments for '{name}' must be a dict or JSON string, got "
                f"{type(raw_arguments).__name__}.",
            )

        # Validate against parameter schema
        schema = tool.parameters_schema
        properties = schema.get("properties", {})
        additional_allowed = schema.get("additionalProperties", True)

        if not additional_allowed:
            extra = set(parsed_args.keys()) - set(properties.keys())
            if extra:
                return (
                    False,
                    {},
                    f"Error: Tool '{name}' does not accept extra arguments: {sorted(extra)}.",
                )

        required = schema.get("required", [])
        missing = set(required) - set(parsed_args.keys())
        if missing:
            return (
                False,
                {},
                f"Error: Tool '{name}' missing required arguments: {sorted(missing)}.",
            )

        for param_name, param_val in parsed_args.items():
            param_spec = properties.get(param_name, {})
            expected_type = param_spec.get("type")
            if expected_type == "string" and not isinstance(param_val, str):
                return (
                    False,
                    {},
                    f"Error: Argument '{param_name}' must be string, got "
                    f"{type(param_val).__name__}.",
                )
            if expected_type == "integer" and (
                not isinstance(param_val, int) or isinstance(param_val, bool)
            ):
                return (
                    False,
                    {},
                    f"Error: Argument '{param_name}' must be integer, got "
                    f"{type(param_val).__name__}.",
                )
            if expected_type == "boolean" and not isinstance(param_val, bool):
                return (
                    False,
                    {},
                    f"Error: Argument '{param_name}' must be boolean, got "
                    f"{type(param_val).__name__}.",
                )
            if "enum" in param_spec and param_val not in param_spec["enum"]:
                return (
                    False,
                    {},
                    f"Error: Argument '{param_name}' must be one of {param_spec['enum']}, "
                    f"got '{param_val}'.",
                )

        return (True, parsed_args, None)

    def execute_tool(
        self,
        name: str,
        validated_args: dict[str, Any],
        backend: SystemBackend,
    ) -> FactEnvelope[Any]:
        """Execute validated tool against the system backend."""
        if name in self._unavailable_tools:
            return FactEnvelope(
                tool=name,
                status="unavailable",
                reason=self._unavailable_tools[name],
                confidence="low",
            )
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' is not registered.")
        return tool.execute(backend, **validated_args)
