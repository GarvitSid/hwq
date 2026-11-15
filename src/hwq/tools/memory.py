"""Memory inspection tools (SRS 4.2, 5, FR-TOOL-1)."""

from __future__ import annotations

from typing import Any

from hwq.exec.allowlist import ALLOWED_COMMANDS
from hwq.facts import FactEnvelope, MemorySummaryFact, MemoryTopologyFact
from hwq.parse.dmidecode import parse_dmidecode_memory
from hwq.parse.meminfo import parse_meminfo
from hwq.protocols import SystemBackend
from hwq.tools.base import Tool


class MemorySummaryTool(Tool):
    """Tool to retrieve RAM and swap metrics from /proc/meminfo."""

    @property
    def name(self) -> str:
        return "get_memory_summary"

    @property
    def description(self) -> str:
        return (
            "Retrieve volatile memory metrics (total, free, available, and swap) "
            "from /proc/meminfo."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, backend: SystemBackend, **kwargs: Any) -> FactEnvelope[MemorySummaryFact]:
        raw = backend.read_text("/proc/meminfo")
        return parse_meminfo(raw)


class MemoryTopologyTool(Tool):
    """Tool to retrieve physical memory slot topology and installed DIMMs via dmidecode."""

    @property
    def name(self) -> str:
        return "get_memory_topology"

    @property
    def description(self) -> str:
        return (
            "Retrieve physical memory slot topology, installed modules, speeds, "
            "and maximum capacity via dmidecode."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, backend: SystemBackend, **kwargs: Any) -> FactEnvelope[MemoryTopologyFact]:
        spec = ALLOWED_COMMANDS["memory_dmi"]
        raw = backend.run(spec)
        return parse_dmidecode_memory(raw)
