"""GPU inspection tool (SRS 4.2, 4.7, 5, FR-TOOL-1, FR-GPU-1, AT-8)."""

from __future__ import annotations

from typing import Any

from hwq.exec.allowlist import ALLOWED_COMMANDS
from hwq.facts import FactEnvelope, GpuFact
from hwq.parse.lspci import parse_gpu_info
from hwq.protocols import SystemBackend
from hwq.tools.base import Tool


class GpuTool(Tool):
    """Tool to inspect GPU controllers and graphics devices using lspci."""

    @property
    def name(self) -> str:
        return "get_gpu_info"

    @property
    def description(self) -> str:
        return (
            "Retrieve graphics controllers, GPU models, discrete/integrated classification, "
            "and kernel driver details via lspci."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, backend: SystemBackend, **kwargs: Any) -> FactEnvelope[GpuFact]:
        spec = ALLOWED_COMMANDS["gpu_lspci"]
        raw = backend.run(spec)
        env = parse_gpu_info(raw)

        # FR-GPU-1 & AT-8: Check for integrated GPUs and attach shared memory caveat
        if env.status == "ok" and isinstance(env.data, GpuFact):
            has_integrated = any(d.is_integrated for d in env.data.devices)
            if has_integrated:
                note = (
                    "Integrated GPU uses shared system memory; dedicated VRAM is not "
                    "reported and dynamically allocated from system RAM."
                )
                if note not in env.caveats:
                    caveats = list(env.caveats) + [note]
                    return FactEnvelope[GpuFact](
                        tool=env.tool,
                        status=env.status,
                        reason=env.reason,
                        source=env.source,
                        privilege=env.privilege,
                        collected_at=env.collected_at,
                        confidence=env.confidence,
                        caveats=caveats,
                        data=env.data,
                    )
        return env
