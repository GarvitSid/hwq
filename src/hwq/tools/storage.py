"""Storage inspection tool (SRS 4.2, 5, FR-TOOL-1)."""

from __future__ import annotations

from typing import Any

from hwq.exec.allowlist import ALLOWED_COMMANDS
from hwq.facts import FactEnvelope, StorageFact
from hwq.parse.lsblk import parse_lsblk
from hwq.protocols import SystemBackend
from hwq.tools.base import Tool


class StorageTool(Tool):
    """Tool to inspect storage block devices using lsblk."""

    @property
    def name(self) -> str:
        return "get_storage_devices"

    @property
    def description(self) -> str:
        return (
            "Retrieve storage block devices (drives, SSDs, NVMe drives, HDDs), "
            "sizes, transport types, and rotation characteristics."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, backend: SystemBackend, **kwargs: Any) -> FactEnvelope[StorageFact]:
        spec = ALLOWED_COMMANDS["storage_lsblk"]
        raw = backend.run(spec)
        return parse_lsblk(raw)
