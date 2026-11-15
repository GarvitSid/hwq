"""CPU inspection tool (SRS 4.2, 5, FR-TOOL-1)."""

from __future__ import annotations

from typing import Any

from hwq.exec.allowlist import ALLOWED_COMMANDS
from hwq.facts import CpuFact, FactEnvelope
from hwq.parse.lscpu import parse_lscpu
from hwq.protocols import SystemBackend
from hwq.tools.base import Tool


class CpuTool(Tool):
    """Tool to inspect CPU hardware facts using lscpu."""

    @property
    def name(self) -> str:
        return "get_cpu_info"

    @property
    def description(self) -> str:
        return (
            "Retrieve CPU architecture, processor model, core and thread counts, "
            "and min/max clock frequencies."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, backend: SystemBackend, **kwargs: Any) -> FactEnvelope[CpuFact]:
        spec = ALLOWED_COMMANDS["cpu_lscpu"]
        raw = backend.run(spec)
        return parse_lscpu(raw)
